// Einsatzbescheinigung – Browser-Version, Hintergrundprozess (Web Worker).
// Lädt Python (Pyodide), die Pakete und die App und führt die Aufrufe der Oberfläche aus.
// Die Daten liegen unter /daten und werden nach jedem Aufruf im IndexedDB des Browsers gesichert.
import { loadPyodide } from "./pyodide/pyodide.mjs";

const VERSION = "__VERSION__";
const basis = new URL("./", import.meta.url);
let py = null;
let aufruf = null;

const status = (text) => postMessage({ art: "status", text });

function sichern(laden) {
  return new Promise((ok, fehler) => py.FS.syncfs(laden, (err) => (err ? fehler(err) : ok())));
}

const bereit = (async () => {
  status("Python wird geladen …");
  const pakete = await (await fetch(new URL(`pakete.json?v=${VERSION}`, basis))).json();
  py = await loadPyodide({ indexURL: new URL("pyodide/", basis).href });

  status("Gespeicherte Daten werden gelesen …");
  py.FS.mkdirTree("/daten");
  py.FS.mount(py.FS.filesystems.IDBFS, {}, "/daten");
  await sichern(true);

  status("Programmteile werden geladen …");
  const wheels = pakete.wheels.map((w) => new URL(`pyodide/${w}`, basis).href);
  await py.loadPackage([...pakete.lock, ...wheels], { messageCallback: () => {} });
  const app = await (await fetch(new URL(`app.zip?v=${VERSION}`, basis))).arrayBuffer();
  py.unpackArchive(app, "zip", { extractDir: "/app" });
  py.runPython(`
import os, sys
sys.path.insert(0, "/app")
os.environ["EINSATZBESCHEINIGUNG_DATEN"] = "/daten"
`);
  aufruf = py.pyimport("einsatzapp.webapi").aufruf;

  status("Daten werden vorbereitet …");
  const start = JSON.parse(aufruf("start", "{}"));
  await sichern(false);
  return start;
})();

async function bearbeite({ id, art, name, argumente, pfad, daten }) {
  try {
    const start = await bereit;
    if (art === "start") {
      postMessage({ id, ...start });
    } else if (art === "aufruf") {
      const antwort = JSON.parse(aufruf(name, JSON.stringify(argumente ?? {})));
      try {
        await sichern(false);
      } catch (err) {
        postMessage({ art: "warnung", text: `Die Daten konnten nicht im Browser gespeichert werden: ${err}` });
      }
      postMessage({ id, ...antwort });
    } else if (art === "schreiben") {
      py.FS.mkdirTree(pfad.slice(0, pfad.lastIndexOf("/")));
      py.FS.writeFile(pfad, new Uint8Array(daten));
      postMessage({ id, ok: true });
    } else if (art === "lesen") {
      const inhalt = py.FS.readFile(pfad);
      postMessage({ id, ok: true, wert: inhalt.buffer }, [inhalt.buffer]);
    } else {
      postMessage({ id, ok: false, fehler: `Unbekannte Anfrage: ${art}` });
    }
  } catch (err) {
    postMessage({ id, ok: false, fehler: String((err && err.stack) || err) });
  }
}

// Aufrufe strikt nacheinander abarbeiten (Python läuft in einem einzigen Thread)
let kette = Promise.resolve();
onmessage = (e) => {
  kette = kette.then(() => bearbeite(e.data));
};
