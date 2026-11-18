// Ende-zu-Ende-Test der Browser-Version: klickt den kompletten Ablauf in einem echten Browser durch.
//
//   npm ci --prefix tests/web && tests/web/node_modules/.bin/playwright install chromium
//   node tests/web/e2e.mjs build/web [bilder-ordner]
//
// BROWSER=chromium (Standard), firefox oder webkit wählt die Browser-Engine.
// Mit CHROME_CHANNEL=chrome wird ein installiertes Google Chrome statt des Playwright-Chromiums verwendet.
import { createServer } from "node:http";
import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { extname, join, resolve, sep } from "node:path";
import { chromium, firefox, webkit } from "playwright";

const SITE = resolve(process.argv[2] || "build/web");
const BILDER = process.argv[3] ? resolve(process.argv[3]) : null;
const TYPEN = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json", ".wasm": "application/wasm", ".zip": "application/zip",
  ".whl": "application/zip", ".png": "image/png",
};

function server() {
  const srv = createServer((req, res) => {
    const pfad = decodeURIComponent(new URL(req.url, "http://x").pathname);
    let datei = resolve(join(SITE, pfad));
    if (datei !== SITE && !datei.startsWith(SITE + sep)) return res.writeHead(403).end();
    try {
      if (statSync(datei).isDirectory()) datei = join(datei, "index.html");
      const inhalt = readFileSync(datei);
      res.writeHead(200, { "Content-Type": TYPEN[extname(datei)] || "application/octet-stream" }).end(inhalt);
    } catch {
      res.writeHead(404).end();
    }
  });
  return new Promise((ok) => srv.listen(0, "127.0.0.1", () => ok(srv)));
}

let schritt = 0;
function ok(bedingung, text) {
  schritt += 1;
  if (!bedingung) throw new Error(`Schritt ${schritt} fehlgeschlagen: ${text}`);
  console.log(`  ✓ ${text}`);
}

async function bild(page, name) {
  if (!BILDER) return;
  mkdirSync(BILDER, { recursive: true });
  await page.screenshot({ path: join(BILDER, `${process.env.BROWSER || "chromium"}-${name}.png`), fullPage: true });
}

async function download(page, ausloeser) {
  const [dl] = await Promise.all([page.waitForEvent("download"), ausloeser()]);
  return { name: dl.suggestedFilename(), daten: readFileSync(await dl.path()) };
}

const knopf = (page, name) => page.getByRole("button", { name, exact: true });
const dialogKnopf = (page, name) => page.locator("dialog[open]").getByRole("button", { name, exact: true });

async function bereit(page) {
  await page.waitForSelector("body[data-bereit='1']", { timeout: 180000 });
}

async function kontaktAnlegen(page, werte) {
  await knopf(page, "+ Neuer Kontakt").click();
  await page.selectOption("#k-anrede", werte.anrede);
  for (const k of ["vorname", "nachname", "dienstgrad", "strasse", "plz", "ort", "email"]) {
    if (werte[k]) await page.fill(`#k-${k}`, werte[k]);
  }
  await knopf(page, "Speichern").click();
  await page.waitForSelector(`#k-meldung.ok`);
}

async function main() {
  const srv = await server();
  const url = `http://127.0.0.1:${srv.address().port}/`;
  const engine = process.env.BROWSER || "chromium";
  const typ = { chromium, firefox, webkit }[engine];
  if (!typ) throw new Error(`Unbekannter Browser: ${engine}`);
  const browser = await typ.launch(engine === "chromium" ? { channel: process.env.CHROME_CHANNEL || undefined } : {});
  const context = await browser.newContext({ acceptDownloads: true, locale: "de-DE", viewport: { width: 1360, height: 900 } });
  const fehler = [];
  const page = await context.newPage();
  page.on("pageerror", (e) => fehler.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") fehler.push(`console: ${m.text()}`); });

  try {
    console.log(`Browser-Test (${engine} ${browser.version()}) gegen ${url}`);
    const t0 = Date.now();
    await page.goto(url);
    await bereit(page);
    ok(true, `App geladen (${((Date.now() - t0) / 1000).toFixed(1)} s)`);
    await bild(page, "1-start");

    // ------------------------------------------------------------ Kontakte
    await page.click("#r-kontakte");
    await kontaktAnlegen(page, { anrede: "Herr", vorname: "Max", nachname: "Mustermann", dienstgrad: "OFM", strasse: "Musterweg 1", plz: "12345", ort: "Musterstadt", email: "max@example.org" });
    await kontaktAnlegen(page, { anrede: "Frau", vorname: "Erika", nachname: "Musterfrau", dienstgrad: "HFF", plz: "12345", ort: "Musterstadt" });
    ok((await page.locator("#k-liste tbody tr").count()) === 2, "zwei Kontakte angelegt");

    const csv = join(tmpdir(), `eb_import_${Date.now()}.csv`);
    writeFileSync(csv, "Anrede;Vorname;Nachname;E-Mail\nFrau;Anna;Beispiel;anna@example.org\nHerr;Max;Mustermann;max@example.org\n");
    const [wahl] = await Promise.all([page.waitForEvent("filechooser"), knopf(page, "Importieren (CSV/Excel) …").click()]);
    await wahl.setFiles(csv);
    await page.waitForSelector("dialog[open] .zuordnung");
    await page.locator("dialog[open]").getByText("2 Kontakte werden übernommen.").waitFor();
    await bild(page, "2-import");
    await dialogKnopf(page, "Importieren").click();
    await page.locator("dialog[open]").getByText("1 Kontakt importiert.").waitFor();
    await dialogKnopf(page, "OK").click();
    ok((await page.locator("#k-liste tbody tr").count()) === 3, "CSV-Import: 1 neu, Dublette übersprungen");

    // ------------------------------------------------------------ Einsatz
    await page.click("#r-einsatz");
    await page.fill("#e-nummer", "2026-117");
    await page.fill("#e-sd", "07.04.2026");
    await page.fill("#e-st", "1159");
    await page.fill("#e-et", "15:00");
    await page.waitForFunction(() => document.querySelector("#e-dauer").textContent.includes("3:01 Std."));
    ok((await page.inputValue("#e-ed")) === "07.04.2026", "Ende-Datum folgt dem Beginn, Dauer wird angezeigt");
    await page.locator("#e-liste tbody tr", { hasText: "Mustermann, Max" }).click();
    await page.locator("#e-liste tbody tr", { hasText: "Musterfrau, Erika" }).click();
    ok((await page.textContent("#e-anzahl")) === "2 von 3 ausgewählt", "zwei Kameraden ausgewählt");
    await bild(page, "3-einsatz");
    await knopf(page, "Weiter: Zeiten prüfen →").click();
    await page.waitForSelector("#einsatz-2:not([hidden])");
    const erika = page.locator("#z-liste tbody tr", { hasText: "Musterfrau, Erika" });
    await erika.locator("input").nth(3).fill("16:30");
    await erika.locator(".dauer", { hasText: "angepasst" }).waitFor();
    ok(true, "Zeit je Kamerad anpassbar (angepasst)");
    await bild(page, "4-zeiten");
    await knopf(page, "PDFs und E-Mail-Entwürfe erstellen").click();
    await page.locator("dialog[open]").getByText("keine E-Mail-Adresse hinterlegt", { exact: false }).waitFor();
    await dialogKnopf(page, "Ja").click();
    await page.locator("dialog[open] h2", { hasText: "2 Bescheinigungen erstellt" }).waitFor({ timeout: 60000 });
    ok(true, "zwei Bescheinigungen erstellt");
    await bild(page, "5-ergebnis");

    const zip = await download(page, () => page.locator("dialog[open]").getByRole("button", { name: /Alles als ZIP/ }).click());
    ok(zip.name === "2026-04-07_1159_Einsatz_2026-117.zip" && zip.daten.subarray(0, 2).toString() === "PK", `ZIP heruntergeladen (${zip.name})`);
    const zeileMax = page.locator("dialog[open] tr", { hasText: "Mustermann, Max" });
    const pdf = await download(page, () => zeileMax.getByRole("button", { name: "PDF", exact: true }).click());
    ok(pdf.daten.subarray(0, 5).toString() === "%PDF-" && pdf.name.endsWith("_Mustermann_Max.pdf"), `PDF heruntergeladen (${pdf.name})`);
    const eml = await download(page, () => zeileMax.getByRole("button", { name: "E-Mail-Entwurf (.eml)" }).click());
    const emlText = eml.daten.toString("latin1");
    ok(emlText.includes("X-Unsent: 1") && emlText.includes("To: max@example.org") && emlText.includes("application/pdf"),
      "E-Mail-Entwurf mit Empfänger und PDF-Anhang");
    const mailto = await zeileMax.getByRole("link", { name: "Im Mailprogramm öffnen" }).getAttribute("href");
    ok(mailto.startsWith("mailto:max@example.org?subject="), "mailto-Link vorhanden");
    ok((await page.locator("dialog[open] tr.warn", { hasText: "Musterfrau, Erika" }).count()) === 1, "ohne E-Mail: nur PDF, Hinweis");

    // ------------------------------------------------------------ Kamerad nachtragen
    await dialogKnopf(page, "Weitere Kameraden ergänzen").click();
    await page.waitForSelector("#e-banner:not([hidden])");
    ok((await page.locator("#e-liste td.status", { hasText: "✓ erstellt am" }).count()) === 2, "gespeicherter Einsatz erkannt, ✓ bei zwei Kameraden");
    await page.locator("#e-liste tbody tr", { hasText: "Beispiel, Anna" }).click();
    await knopf(page, "Weiter: Zeiten prüfen →").click();
    await page.waitForSelector("#einsatz-2:not([hidden])");
    ok((await page.textContent("#z-kopf")).includes("Ergänzung – 2 bereits bescheinigt"), "Schritt 2 zeigt Ergänzung");
    await knopf(page, "PDFs und E-Mail-Entwürfe erstellen").click();
    await page.locator("dialog[open] h2", { hasText: "der Einsatz hat jetzt 3 Bescheinigungen" }).waitFor({ timeout: 60000 });
    ok(true, "Anna nachgetragen – Einsatz hat jetzt 3 Bescheinigungen");
    await dialogKnopf(page, "Schließen").click();

    // ------------------------------------------------------------ Speicherung im Browser
    await page.reload();
    await bereit(page);
    await page.click("#r-verlauf");
    await page.locator("#v-liste tbody tr", { hasText: "2026-117" }).waitFor();
    ok((await page.locator("#v-liste tbody tr td").nth(3).textContent()) === "3", "nach Neuladen: Einsatz mit 3 Bescheinigungen gespeichert");
    await page.waitForFunction(() => document.querySelectorAll("#v-details tbody tr").length === 3);
    ok(true, "Details: drei Kameraden");
    await bild(page, "6-verlauf");
    const paket = await download(page, () => knopf(page, "PDFs herunterladen (ZIP)").click());
    ok(paket.daten.subarray(0, 2).toString() === "PK", "ZIP aller PDFs aus dem Verlauf");
    await knopf(page, "Sammel-PDF ansehen").click();
    await page.waitForSelector("dialog[open].pdf iframe");
    ok(true, "Sammel-PDF wird angezeigt");
    await dialogKnopf(page, "Schließen").click();

    // ------------------------------------------------------------ Vorlage
    await page.click("#r-vorlage");
    await page.fill("#vl-titel", "Bescheinigung über die Teilnahme an einem Einsatz der Feuerwehr");
    await page.click("#r-einsatz");
    await page.locator("dialog[open]").getByText("Die Vorlage wurde geändert").waitFor();
    await dialogKnopf(page, "Abbrechen").click();
    ok(await page.isVisible("#s-vorlage"), "ungespeicherte Vorlage: Rückfrage beim Wechseln");
    await knopf(page, "Speichern").click();
    await page.waitForSelector("#vl-status.ok");
    await knopf(page, "Vorschau-PDF ansehen").click();
    await page.waitForSelector("dialog[open].pdf iframe");
    await bild(page, "7-vorschau");
    await dialogKnopf(page, "Schließen").click();
    ok(true, "Vorlage gespeichert und Vorschau angezeigt");
    await bild(page, "8-vorlage");

    // ------------------------------------------------------------ Einstellungen
    await page.click("#r-einstellungen");
    await page.waitForFunction(() => document.querySelector("#s-speicher").textContent.includes("3 Kontakte"));
    const sicherung = await download(page, () => knopf(page, "Datensicherung herunterladen").click());
    ok(sicherung.name.startsWith("Einsatzbescheinigung_Datensicherung_") && sicherung.daten.subarray(0, 2).toString() === "PK",
      "Datensicherung heruntergeladen");
    await knopf(page, "Lizenzen …").click();
    const lizenz = await page.locator("dialog[open] pre.lizenzen").textContent();
    ok(lizenz.includes("MIT License") && lizenz.includes("Mozilla Public License") && lizenz.includes("GNU LESSER"),
      "Lizenztexte vollständig");
    await dialogKnopf(page, "OK").click();
    await bild(page, "9-einstellungen");

    // ------------------------------------------------------------ zweiter Tab
    const zweiter = await context.newPage();
    await zweiter.goto(url);
    await zweiter.getByText("bereits in einem anderen Tab").waitFor({ timeout: 30000 });
    ok(true, "zweiter Tab wird abgewiesen");
    await zweiter.close();

    ok(fehler.length === 0, `keine Fehler in der Browser-Konsole${fehler.length ? `:\n${fehler.join("\n")}` : ""}`);
    console.log(`Alle ${schritt} Prüfungen bestanden.`);
  } catch (err) {
    await bild(page, "fehler").catch(() => {});
    console.error(err.message);
    if (fehler.length) console.error(fehler.join("\n"));
    process.exitCode = 1;
  } finally {
    await browser.close();
    srv.close();
  }
}

main();
