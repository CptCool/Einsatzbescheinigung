"use strict";
// Einsatzbescheinigung – Browser-Version: die Oberfläche.
// Gerechnet und erzeugt wird in Python (worker.js → einsatzapp/webapi.py), mit demselben Code
// wie in der Desktop-App. Gesendet wird nie automatisch – E-Mails verschickt der Nutzer selbst.

const VERSION = document.documentElement.dataset.version;

// ============================================================================ Hilfsfunktionen
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

function h(tag, attrs = {}, ...kinder) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const kind of kinder.flat(Infinity)) {
    if (kind != null && kind !== false) el.append(kind instanceof Node ? kind : String(kind));
  }
  return el;
}

function entprellt(fn, ms = 150) {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}

const heute = () => new Date().toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
const klein = (s) => String(s || "").toLocaleLowerCase("de");
function anzeigeName(k) {
  return `${k.nachname || ""}, ${k.vorname || ""}`.replace(/^[,\s]+|[,\s]+$/g, "") || "(ohne Namen)";
}

// ============================================================================ Verbindung zu Python
class Hinweis extends Error {}

let worker = null;
let naechsteId = 1;
const offen = new Map();

function senden(nachricht, transfer = []) {
  return new Promise((ok, fehler) => {
    const id = naechsteId++;
    offen.set(id, { ok, fehler });
    worker.postMessage({ id, ...nachricht }, transfer);
  });
}

function antwort(e) {
  const d = e.data;
  if (d.art === "status") {
    $("#laden-text").textContent = d.text;
    return;
  }
  if (d.art === "warnung") {
    const leiste = $("#warnung");
    leiste.textContent = d.text;
    leiste.hidden = false;
    return;
  }
  const wartend = offen.get(d.id);
  if (!wartend) return;
  offen.delete(d.id);
  if (d.ok) wartend.ok(d.wert);
  else if (d.meldung) wartend.fehler(new Hinweis(d.meldung));
  else wartend.fehler(new Error(d.fehler || "Unbekannter Fehler"));
}

const py = (name, argumente = {}) => senden({ art: "aufruf", name, argumente });

async function hochladen(datei) {
  const name = datei.name.replace(/[\\/]/g, "_");
  const pfad = `/tmp/upload/${Date.now()}_${Math.random().toString(36).slice(2)}/${name}`;
  const daten = await datei.arrayBuffer();
  await senden({ art: "schreiben", pfad, daten }, [daten]);
  return pfad;
}

const TYPEN = { pdf: "application/pdf", zip: "application/zip", eml: "message/rfc822", csv: "text/csv" };
async function blob(pfad, name) {
  const daten = await senden({ art: "lesen", pfad });
  const endung = name.split(".").pop().toLowerCase();
  return new Blob([daten], { type: TYPEN[endung] || "application/octet-stream" });
}

async function herunterladen(pfad, name) {
  const url = URL.createObjectURL(await blob(pfad, name));
  const a = h("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 120000);
}

async function pdfAnsehen(pfad, name, titel) {
  const url = URL.createObjectURL(await blob(pfad, name));
  await dialog({
    titel, klasse: "pdf", inhalt: h("iframe", { src: url, title: titel }),
    knoepfe: [{ text: "Herunterladen", aktion: () => herunterladen(pfad, name) },
      { text: "Schließen", wert: true, art: "primaer" }],
  });
  URL.revokeObjectURL(url);
}

function dateiWaehlen(accept) {
  return new Promise((fertig) => {
    const inp = h("input", { type: "file", accept, hidden: true });
    inp.addEventListener("change", () => { fertig(inp.files[0] || null); inp.remove(); });
    inp.addEventListener("cancel", () => { fertig(null); inp.remove(); });
    document.body.append(inp);
    inp.click();
  });
}

// ============================================================================ Dialoge
function dialog({ titel, text, inhalt, details, knoepfe, klasse = "", abbruch = null }) {
  knoepfe = knoepfe || [{ text: "OK", wert: true, art: "primaer" }];
  return new Promise((fertig) => {
    const dlg = h("dialog", { class: `dlg ${klasse}` });
    const schliessen = (wert) => {
      dlg.close();
      dlg.remove();
      fertig(wert);
    };
    const leiste = h("div", { class: "knopfleiste" }, h("span", { class: "platz" }));
    for (const k of knoepfe) {
      leiste.append(h("button", {
        type: "button", class: k.art || "", text: k.text,
        onclick: k.aktion ? sicher(() => k.aktion(schliessen)) : () => schliessen(k.wert),
      }));
    }
    dlg.append(...[h("h2", { text: titel }), text ? h("p", { class: "dlg-text", text }) : null, inhalt,
      details ? h("pre", { class: "details", text: details }) : null, leiste].filter(Boolean));
    dlg.addEventListener("cancel", (e) => {
      e.preventDefault();
      schliessen(abbruch);
    });
    document.body.append(dlg);
    dlg.showModal();
    (dlg.querySelector("button.primaer") || leiste.querySelector("button"))?.focus();
  });
}

const meldung = (titel, text) => dialog({ titel, text });
const frage = (text, titel = "Bitte bestätigen") => dialog({
  titel, text, abbruch: false,
  knoepfe: [{ text: "Nein", wert: false }, { text: "Ja", wert: true, art: "primaer" }],
});
const speichernFrage = (text) => dialog({
  titel: "Ungespeicherte Änderungen", text, abbruch: "abbrechen",
  knoepfe: [{ text: "Abbrechen", wert: "abbrechen" }, { text: "Verwerfen", wert: "verwerfen" },
    { text: "Speichern", wert: "speichern", art: "primaer" }],
});

function zeigeFehler(err) {
  if (err instanceof Hinweis) return meldung("Bitte prüfen", err.message);
  console.error(err);
  return dialog({
    titel: "Unerwarteter Fehler",
    text: "Das hätte nicht passieren dürfen. Falls es wieder auftritt, bitte die Details unten weitergeben "
      + "(z. B. als „Issue“ auf GitHub).",
    details: String(err && err.message ? err.message : err),
  });
}

function sicher(fn) {
  return async (...a) => {
    try {
      return await fn(...a);
    } catch (err) {
      zeigeFehler(err);
      return undefined;
    }
  };
}

async function mitWarten(text, arbeit) {
  $("#warten-text").textContent = text;
  const timer = setTimeout(() => { $("#warten").hidden = false; }, 200);
  try {
    return await arbeit();
  } finally {
    clearTimeout(timer);
    $("#warten").hidden = true;
  }
}

// ============================================================================ Zustand und Reiter
let info = null; // Grunddaten aus Python (Felder, Platzhalter, Standardtexte …)
const zustand = { kontakte: [], einstellungen: {} };
const SEITEN = ["einsatz", "verlauf", "kontakte", "vorlage", "einstellungen"];
let aktiv = "einsatz";

async function zeigeSeite(name) {
  if (name === aktiv) return true;
  const alt = { kontakte: Kontakte, vorlage: Vorlage }[aktiv];
  if (alt && !(await alt.verlassen())) return false;
  aktiv = name;
  for (const s of SEITEN) {
    $(`#s-${s}`).hidden = s !== name;
    $(`#r-${s}`).setAttribute("aria-selected", String(s === name));
  }
  if (name === "verlauf") await Verlauf.aktualisieren();
  if (name === "einstellungen") await Einstellungen.speicherAnzeigen();
  return true;
}

async function kontakteGeaendert() {
  zustand.kontakte = await py("kontakte");
  Kontakte.liste();
  Einsatz.liste();
}

async function einsaetzeGeaendert() {
  await Einsatz.pruefen();
  await Verlauf.aktualisieren();
}

// ============================================================================ Einsatz
const Einsatz = {
  auswahl: new Set(),
  anpassungen: new Map(),
  schluessel: null,
  endeManuell: false,
  treffer: null,
  vorbereitung: null,
  zeilenEl: new Map(),

  init() {
    this.feld = {
      nummer: $("#e-nummer"), sd: $("#e-sd"), st: $("#e-st"), ed: $("#e-ed"), et: $("#e-et"), ausst: $("#e-ausst"),
    };
    this.feld.sd.value = this.feld.ed.value = this.feld.ausst.value = heute();
    const pruefen = entprellt(() => this.pruefen().catch(zeigeFehler), 120);
    this.feld.sd.addEventListener("input", () => {
      if (!this.endeManuell) this.feld.ed.value = this.feld.sd.value;
      pruefen();
    });
    this.feld.ed.addEventListener("keydown", () => { this.endeManuell = true; });
    for (const k of ["nummer", "st", "ed", "et"]) this.feld[k].addEventListener("input", pruefen);
    $("#e-filter").addEventListener("input", () => this.liste());
    $("#e-alle").addEventListener("click", () => this.alle(true));
    $("#e-keine").addEventListener("click", () => this.keine());
    $("#e-alle-cb").addEventListener("change", (e) => this.alle(e.target.checked));
    $("#e-neu").addEventListener("click", () => this.neu());
    $("#e-banner-neu").addEventListener("click", () => this.neu());
    $("#e-verlauf").addEventListener("click", sicher(() => zeigeSeite("verlauf")));
    $("#e-weiter").addEventListener("click", sicher(() => this.weiter()));
    $("#z-zurueck").addEventListener("click", () => this.seite(1));
    $("#z-erstellen").addEventListener("click", sicher(() => this.erstellen()));
    this.zeilenPruefenSpaeter = entprellt(() => this.zeilenPruefen().catch(zeigeFehler), 150);
    this.liste();
  },

  werte() {
    return Object.fromEntries(Object.entries(this.feld).map(([k, el]) => [k, el.value]));
  },

  seite(n) {
    $("#einsatz-1").hidden = n !== 1;
    $("#einsatz-2").hidden = n !== 2;
    window.scrollTo(0, 0);
  },

  liste() {
    const filt = klein($("#e-filter").value.trim());
    const ids = new Set(zustand.kontakte.map((k) => k.id));
    for (const id of [...this.auswahl]) if (!ids.has(id)) this.auswahl.delete(id);
    const status = this.treffer?.status || {};
    const zeilen = [];
    for (const k of zustand.kontakte) {
      if (filt && !klein(`${k.vorname} ${k.nachname} ${k.dienstgrad} ${k.email}`).includes(filt)) continue;
      const cb = h("input", { type: "checkbox", "aria-label": `${anzeigeName(k)} auswählen` });
      cb.checked = this.auswahl.has(k.id);
      const tr = h("tr", { dataset: { id: k.id } },
        h("td", { class: "sel" }, cb), h("td", { text: anzeigeName(k) }), h("td", { text: k.dienstgrad }),
        h("td", { text: k.email || "– keine E-Mail –" }), h("td", { class: "status", text: status[k.id] || "" }));
      tr.classList.toggle("an", cb.checked);
      tr.classList.toggle("ohne-mail", !k.email);
      tr.addEventListener("click", () => this.setze(k.id, !this.auswahl.has(k.id)));
      zeilen.push(tr);
    }
    $("#e-liste tbody").replaceChildren(...zeilen);
    $("#e-leer").hidden = zustand.kontakte.length > 0;
    this.zaehle();
  },

  setze(id, an) {
    if (an) this.auswahl.add(id);
    else this.auswahl.delete(id);
    const tr = $(`#e-liste tbody tr[data-id="${CSS.escape(id)}"]`);
    if (tr) {
      tr.classList.toggle("an", an);
      tr.querySelector("input").checked = an;
    }
    this.zaehle();
  },

  alle(an) {
    for (const tr of $$("#e-liste tbody tr")) this.setze(tr.dataset.id, an);
    this.zaehle();
  },

  keine() {
    for (const id of [...this.auswahl]) this.setze(id, false);
    this.zaehle();
  },

  zaehle() {
    $("#e-anzahl").textContent = `${this.auswahl.size} von ${zustand.kontakte.length} ausgewählt`;
    const sichtbar = $$("#e-liste tbody tr").map((tr) => tr.dataset.id);
    const gewaehlt = sichtbar.filter((id) => this.auswahl.has(id)).length;
    const cb = $("#e-alle-cb");
    cb.checked = sichtbar.length > 0 && gewaehlt === sichtbar.length;
    cb.indeterminate = gewaehlt > 0 && gewaehlt < sichtbar.length;
  },

  async pruefen() {
    const w = this.werte();
    const r = await py("einsatz_pruefen", { nummer: w.nummer, sd: w.sd, st: w.st, ed: w.ed, et: w.et });
    if (JSON.stringify(w) !== JSON.stringify(this.werte())) return; // inzwischen weitergetippt
    const dauer = $("#e-dauer");
    dauer.textContent = r.fehler || r.dauer;
    dauer.className = r.fehler ? "fehler" : "info";
    this.treffer = r.treffer;
    $("#e-banner").hidden = !r.treffer;
    if (r.treffer) {
      const n = r.treffer.anzahl;
      $("#e-banner-text").textContent = `Dieser Einsatz ist bereits gespeichert: ${n} Kamerad${n !== 1 ? "en haben" : " hat"} `
        + "schon eine Bescheinigung (✓ in der Liste). Wähle die Kameraden aus, die ergänzt werden sollen – "
        + "die vorhandenen Bescheinigungen bleiben erhalten.";
    }
    $("#e-liste").classList.toggle("mit-status", Boolean(r.treffer));
    for (const tr of $$("#e-liste tbody tr")) {
      tr.querySelector(".status").textContent = r.treffer?.status[tr.dataset.id] || "";
    }
  },

  neu() {
    this.endeManuell = false;
    this.feld.nummer.value = this.feld.st.value = this.feld.et.value = "";
    this.feld.sd.value = this.feld.ed.value = this.feld.ausst.value = heute();
    $("#e-filter").value = "";
    this.auswahl.clear();
    this.anpassungen.clear();
    this.schluessel = null;
    this.liste();
    this.seite(1);
    this.pruefen().catch(zeigeFehler);
    this.feld.nummer.focus();
  },

  laden(d) {
    this.endeManuell = true;
    for (const k of ["nummer", "sd", "st", "ed", "et", "ausst"]) this.feld[k].value = d[k];
    $("#e-filter").value = "";
    this.auswahl.clear();
    this.anpassungen.clear();
    this.schluessel = null;
    this.liste();
    this.seite(1);
    return this.pruefen();
  },

  async weiter() {
    const w = this.werte();
    const v = await py("weiter", { ...w, auswahl: [...this.auswahl] });
    if (v.ende_datum) {
      this.endeManuell = true;
      this.feld.ed.value = v.ende_datum;
    }
    for (const f of v.fragen) if (!(await frage(f))) return;
    const schluessel = JSON.stringify(v.schluessel);
    if (schluessel !== this.schluessel) {
      this.anpassungen.clear();
      this.schluessel = schluessel;
    }
    this.vorbereitung = { ...v, nummer: w.nummer, ausst: w.ausst };
    for (const z of v.zeilen) {
      if (!this.anpassungen.has(z.id)) this.anpassungen.set(z.id, { ...(z.gespeichert || v.standard) });
    }
    this.zeilenBauen();
    this.seite(2);
    await this.zeilenPruefen();
  },

  zeilenBauen() {
    const v = this.vorbereitung;
    this.zeilenEl = new Map();
    const zeilen = v.zeilen.map((z) => {
      const werte = this.anpassungen.get(z.id);
      const inp = {};
      for (const [k, cls, was] of [["sd", "datum", "Beginn Datum"], ["st", "uhr", "Beginn Uhrzeit"],
        ["ed", "datum", "Ende Datum"], ["et", "uhr", "Ende Uhrzeit"]]) {
        inp[k] = h("input", { class: cls, value: werte[k], autocomplete: "off", "aria-label": `${was} ${z.name}` });
        inp[k].addEventListener("input", () => {
          werte[k] = inp[k].value;
          this.zeilenPruefenSpaeter();
        });
      }
      const dauer = h("span", { class: "dauer" });
      const zurueck = h("button", {
        type: "button", class: "klein", title: "Einsatzzeit wiederherstellen", text: "↺",
        onclick: () => {
          for (const k of Object.keys(inp)) inp[k].value = werte[k] = v.standard[k];
          this.zeilenPruefen().catch(zeigeFehler);
        },
      });
      this.zeilenEl.set(z.id, dauer);
      return h("tr", {}, h("td", { text: z.name }), h("td", {}, inp.sd, " ", inp.st), h("td", {}, inp.ed, " ", inp.et),
        h("td", {}, dauer), h("td", {}, zurueck), h("td", { class: z.email ? "info" : "fehler", text: z.hinweis }));
    });
    $("#z-liste tbody").replaceChildren(...zeilen);
    $("#z-kopf").textContent = `${v.kopf}   –   Abweichende Zeiten einfach überschreiben; ↺ stellt die Einsatzzeit wieder her.`;
    $("#z-mails").checked = zustand.einstellungen.mails_erstellen;
    $("#z-sammel").checked = zustand.einstellungen.sammel_pdf;
    $("#z-sammel-text").textContent = v.ergaenzung ? "Sammel-PDF für die Ablage aktualisieren (alle Kameraden)"
      : "Sammel-PDF für die Ablage erstellen";
    $("#z-mails-info").textContent = "als .eml-Dateien mit PDF-Anhang"
      + (v.bcc.length ? ` · Kopie (BCC) an ${v.bcc.join(", ")}` : "");
  },

  async zeilenPruefen() {
    const v = this.vorbereitung;
    const zeilen = Object.fromEntries(v.zeilen.map((z) => [z.id, this.anpassungen.get(z.id)]));
    const r = await py("zeilen_pruefen", { standard: v.standard, zeilen });
    for (const [id, s] of Object.entries(r)) {
      const el = this.zeilenEl.get(id);
      if (el) {
        el.textContent = s.text;
        el.className = `dauer ${s.art}`;
      }
    }
  },

  async erstellen() {
    if (Vorlage.istGeaendert() && !(await Vorlage.verlassen())) return;
    const v = this.vorbereitung;
    const zeilen = v.zeilen.map((z) => ({ id: z.id, ...this.anpassungen.get(z.id) }));
    const mails = $("#z-mails").checked;
    const sammel = $("#z-sammel").checked;
    const p = await py("erstellen_pruefen", { zeilen, mails });
    for (const f of p.fragen) if (!(await frage(f))) return;
    const r = await mitWarten("Bescheinigungen werden erstellt …",
      () => py("erstellen", { nummer: v.nummer, ...v.standard, ausst: v.ausst, zeilen, mails, sammel }));
    this.keine(); // die Kameraden stehen jetzt als „✓ erstellt“ in der Liste
    await einsaetzeGeaendert();
    const weiter = await Ergebnis.zeigen(r);
    if (weiter === "neu") this.neu();
    else if (weiter === "ergaenzen") this.seite(1);
  },
};

// ============================================================================ Ergebnis
// Ein Browser darf keine Datei an einen mailto-Link hängen (das kann kein Mailprogramm mehr, aus Sicherheitsgründen).
// Deshalb drei Wege, die funktionieren:
//  1. „E-Mail öffnen“ (Empfänger, Betreff, Text) und das PDF als Kachel ins Mail-Fenster ziehen – Chrome/Edge legen
//     die Datei dabei selbst in ihrem Temp-Ordner ab (Drag-Typ „DownloadURL“).
//  2. „Teilen …“: PDF samt Betreff und Text über das Teilen-Menü des Systems (Web Share API); die Adresse kommt
//     in die Zwischenablage.
//  3. „E-Mail-Entwurf (.eml)“: fertiger Entwurf mit Anhang – Outlook (klassisch) und Thunderbird öffnen ihn direkt.
const ZIEHEN_MOEGLICH = Boolean(navigator.userAgentData?.brands?.some((b) => /Chromium|Google Chrome|Microsoft Edge/.test(b.brand)));

const Ergebnis = {
  async zeigen(r) {
    const urls = [];
    const pdfs = await Promise.all(r.zeilen.map(async (z) => {
      const b = await blob(z.pdf, z.pdf_name);
      const url = URL.createObjectURL(b);
      urls.push(url);
      return { url, datei: new File([b], z.pdf_name, { type: "application/pdf" }) };
    }));
    const teilenMoeglich = pdfs.length > 0 && Boolean(navigator.canShare?.({ files: [pdfs[0].datei] }));
    const meldungEl = h("p", { class: "info", "aria-live": "polite" });

    const teilen = async (z, datei) => {
      let kopiert = false;
      if (z.email) {
        try {
          await navigator.clipboard.writeText(z.email);
          kopiert = true;
        } catch { /* Zwischenablage nicht erlaubt */ }
      }
      meldungEl.textContent = z.email ? (kopiert ? `Empfänger ${z.email} liegt in der Zwischenablage – im Mail-Fenster bei „An“ einfügen.`
        : `Empfänger im Mail-Fenster bei „An“ eintragen: ${z.email}`) : "";
      try {
        await navigator.share({ files: [datei], title: z.betreff, text: z.text });
      } catch (err) {
        if (err.name !== "AbortError") throw new Hinweis(`Teilen ist hier nicht möglich (${err.message}). Bitte einen der anderen Wege nutzen.`);
      }
    };

    const zeilen = r.zeilen.map((z, i) => {
      const { url, datei } = pdfs[i];
      const kachel = ZIEHEN_MOEGLICH ? h("span", {
        class: "kachel", draggable: "true", role: "img", "aria-label": `PDF ${z.pdf_name} zum Hineinziehen`,
        title: "Nach „E-Mail öffnen“ diese Kachel mit der Maus in das Mail-Fenster ziehen – das PDF wird angehängt.",
      }, "📄 PDF hineinziehen") : null;
      kachel?.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("DownloadURL", `application/pdf:${z.pdf_name}:${url}`);
        e.dataTransfer.setData("text/uri-list", url);
        e.dataTransfer.effectAllowed = "copy";
      });
      const aktionen = [
        z.mailto ? h("a", { class: "knopf klein", href: z.mailto, title: "Neue Mail mit Empfänger, Betreff und Text im Standard-Mailprogramm" }, "✉ E-Mail öffnen") : null,
        z.mailto ? kachel : null,
        z.eml ? h("button", {
          type: "button", class: "klein", title: "Fertiger Entwurf mit PDF-Anhang – Outlook (klassisch) und Thunderbird öffnen ihn per Doppelklick",
          onclick: sicher(() => herunterladen(z.eml, z.eml_name)),
        }, "E-Mail-Entwurf (.eml)") : null,
        teilenMoeglich && z.mailto ? h("button", {
          type: "button", class: "klein", title: "PDF mit Betreff und Text an Mail oder Outlook übergeben (Teilen-Menü des Systems)",
          onclick: sicher(() => teilen(z, datei)),
        }, "Teilen …") : null,
        h("button", { type: "button", class: "klein", onclick: sicher(() => herunterladen(z.pdf, z.pdf_name)) }, "PDF"),
      ];
      return h("tr", { class: z.ok ? "" : "warn" },
        h("td", {}, `${z.ok ? "✓" : "⚠"}  ${z.name}`,
          h("div", { class: "hinweis", text: z.email || (r.mails ? "keine E-Mail-Adresse – nur PDF" : "") })),
        h("td", { class: "aktionen" }, aktionen));
    });

    const wege = [];
    if (ZIEHEN_MOEGLICH) wege.push("„✉ E-Mail öffnen“ klicken (Empfänger, Betreff und Text sind ausgefüllt) und dann die Kachel „📄 PDF hineinziehen“ mit der Maus in das Mail-Fenster ziehen.");
    wege.push("„E-Mail-Entwurf (.eml)“ herunterladen und öffnen – Outlook (klassisch) und Thunderbird zeigen einen fertigen Entwurf mit Anhang.");
    if (teilenMoeglich) wege.push("„Teilen …“ übergibt PDF, Betreff und Text an Mail oder Outlook; die E-Mail-Adresse liegt dann in der Zwischenablage.");
    if (!ZIEHEN_MOEGLICH) wege.push("„✉ E-Mail öffnen“ startet eine neue Mail mit Text – das PDF (Knopf „PDF“) dann selbst anhängen. In Chrome und Edge lässt sich das PDF auch direkt in die Mail ziehen.");

    const hinweise = r.hinweise.map((t) => h("p", { class: "fehler", text: `⚠  ${t}` }));
    const sicherung = Einstellungen.letzteSicherung();
    const erinnerung = !sicherung || Date.now() - sicherung > 14 * 86400000
      ? h("p", { class: "hinweis", text: "Tipp: Unter „Einstellungen“ regelmäßig eine Datensicherung herunterladen." }) : null;
    const inhalt = h("div", {},
      r.mails ? h("p", { class: "info", text: "Die E-Mails wurden NICHT gesendet. Bitte jede E-Mail prüfen und selbst auf „Senden“ klicken." }) : null,
      h("div", { class: "ergebnis-aktionen" },
        h("button", { type: "button", class: "primaer", onclick: sicher(() => herunterladen(r.zip, r.zip_name)) },
          r.mails ? "Alles als ZIP herunterladen (PDFs und E-Mail-Entwürfe)" : "Alle PDFs als ZIP herunterladen"),
        r.sammel ? h("button", { type: "button", onclick: sicher(() => pdfAnsehen(r.sammel, r.sammel_name, "Sammel-PDF")) },
          `Sammel-PDF ansehen (${r.gesamt} Bescheinigung${r.gesamt !== 1 ? "en" : ""})`) : null),
      h("div", { class: "tabelle-rahmen ergebnis-liste" }, h("table", { class: "liste kompakt" }, h("tbody", {}, zeilen))),
      meldungEl,
      hinweise,
      r.mails ? h("div", { class: "hinweis" }, h("p", { text: "So kommt das PDF in die E-Mail – je nach Mailprogramm:" }),
        h("ul", {}, wege.map((w) => h("li", { text: w })))) : null,
      h("p", { class: "hinweis", text: "Der Einsatz ist gespeichert. Vergessene Kameraden lassen sich jederzeit über „Weitere Kameraden ergänzen“ oder „Gespeicherte Einsätze“ nachtragen." }),
      erinnerung);
    try {
      return await dialog({
        titel: r.titel, klasse: "breit", inhalt, abbruch: "schliessen",
        knoepfe: [{ text: "Neuer Einsatz", wert: "neu" }, { text: "Weitere Kameraden ergänzen", wert: "ergaenzen" },
          { text: "Schließen", wert: "schliessen", art: "primaer" }],
      });
    } finally {
      for (const url of urls) URL.revokeObjectURL(url);
    }
  },
};

// ============================================================================ Gespeicherte Einsätze
const Verlauf = {
  gewaehlt: null,
  liste: [],

  init() {
    $("#v-filter").addEventListener("input", entprellt(() => this.aktualisieren().catch(zeigeFehler), 150));
    $("#v-ergaenzen").addEventListener("click", sicher(() => this.ergaenzen()));
    $("#v-zip").addEventListener("click", sicher(async () => {
      const r = await mitWarten("ZIP wird erstellt …", () => py("einsatz_paket", { id: this.gewaehlt }));
      await herunterladen(r.pfad, r.name);
    }));
    $("#v-sammel").addEventListener("click", sicher(async () => {
      const r = await mitWarten("Sammel-PDF wird erstellt …", () => py("einsatz_sammel", { id: this.gewaehlt }));
      await pdfAnsehen(r.pfad, r.name, "Sammel-PDF");
    }));
    $("#v-entfernen").addEventListener("click", sicher(() => this.entfernen()));
  },

  async aktualisieren() {
    this.liste = await py("einsaetze", { filter: $("#v-filter").value });
    const zeilen = this.liste.map((e) => {
      const tr = h("tr", { dataset: { id: e.id } }, h("td", { text: e.datum }), h("td", { text: e.zeit }),
        h("td", { text: e.nummer }), h("td", { text: e.anzahl }), h("td", { text: e.geaendert }));
      tr.addEventListener("click", sicher(() => this.waehlen(e.id)));
      tr.addEventListener("dblclick", sicher(() => this.ergaenzen()));
      return tr;
    });
    $("#v-liste tbody").replaceChildren(...zeilen);
    const leer = $("#v-leer");
    leer.hidden = this.liste.length > 0;
    leer.replaceChildren(...($("#v-filter").value.trim() ? ["Kein gespeicherter Einsatz passt zur Suche."]
      : ["Noch keine Einsätze gespeichert.", h("br"), "Sobald im Bereich „Einsatz“ Bescheinigungen erstellt werden, erscheint der Einsatz hier."]));
    const ids = this.liste.map((e) => e.id);
    await this.waehlen(ids.includes(this.gewaehlt) ? this.gewaehlt : ids[0] || null);
  },

  async waehlen(id) {
    this.gewaehlt = id;
    for (const tr of $$("#v-liste tbody tr")) tr.classList.toggle("gewaehlt", tr.dataset.id === id);
    for (const b of ["#v-ergaenzen", "#v-zip", "#v-sammel", "#v-entfernen"]) $(b).disabled = !id;
    if (!id) {
      $("#v-details tbody").replaceChildren();
      return;
    }
    const d = await py("einsatz_details", { id });
    $("#v-details tbody").replaceChildren(...d.teilnehmer.map((t) => h("tr", { class: t.vorhanden ? "" : "fehlt" },
      h("td", { text: t.name }), h("td", { text: t.dienstgrad }), h("td", { text: t.zeit }), h("td", { text: t.erstellt }),
      h("td", { text: t.vorhanden ? "gespeichert" : "fehlt" }))));
    const vorhanden = d.teilnehmer.some((t) => t.vorhanden);
    $("#v-zip").disabled = $("#v-sammel").disabled = !vorhanden;
  },

  async ergaenzen() {
    if (!this.gewaehlt) return;
    const d = await py("einsatz_laden", { id: this.gewaehlt });
    if (await zeigeSeite("einsatz")) await Einsatz.laden(d);
  },

  async entfernen() {
    const e = this.liste.find((x) => x.id === this.gewaehlt);
    if (!e) return;
    const ok = await frage(`Einsatz ${e.nummer} vom ${e.datum} entfernen?\n\nDer Eintrag und die gespeicherten PDFs werden aus diesem Browser gelöscht. `
      + "Bereits heruntergeladene Dateien sind nicht betroffen. Danach lassen sich zu diesem Einsatz keine Kameraden mehr ergänzen.",
    "Einsatz entfernen");
    if (!ok) return;
    await py("einsatz_entfernen", { id: e.id });
    await einsaetzeGeaendert();
  },
};

// ============================================================================ Kontakte
const Kontakte = {
  aktuell: null,
  original: "",
  felder: {},

  init() {
    const form = $("#k-form");
    const dienstgrade = h("datalist", { id: "k-dienstgrade" }, info.dienstgrade.map((d) => h("option", { value: d })));
    for (const [key, label] of info.kontakt_formular) {
      let el;
      if (key === "anrede") el = h("select", { class: "kurz" }, info.anreden.map((a) => h("option", { value: a, text: a })));
      else if (key === "dienstgrad") el = h("input", { class: "kurz", list: "k-dienstgrade" });
      else if (key === "plz") el = h("input", { class: "kurz", inputmode: "numeric" });
      else el = h("input", { type: key === "email" ? "email" : "text" });
      el.id = `k-${key}`;
      this.felder[key] = el;
      form.append(h("label", { for: el.id, text: label }), el);
    }
    form.append(dienstgrade);
    form.addEventListener("submit", sicher(async (e) => {
      e.preventDefault();
      await this.speichern();
    }));
    $("#k-verwerfen").addEventListener("click", () => this.verwerfen());
    $("#k-neu").addEventListener("click", sicher(() => this.neu()));
    $("#k-loeschen").addEventListener("click", sicher(() => this.loeschen()));
    $("#k-import").addEventListener("click", sicher(() => this.importieren()));
    $("#k-export").addEventListener("click", sicher(async () => {
      const r = await py("kontakte_exportieren");
      await herunterladen(r.pfad, r.name);
    }));
    $("#k-filter").addEventListener("input", () => this.liste());
    this.leer();
    this.liste();
  },

  formWerte() {
    const w = Object.fromEntries(Object.entries(this.felder).map(([k, el]) => [k, el.value.trim()]));
    if (w.anrede === "keine Angabe") w.anrede = "";
    return w;
  },

  setzeForm(werte) {
    for (const [k, el] of Object.entries(this.felder)) {
      el.value = k === "anrede" ? (werte.anrede || "keine Angabe") : (werte[k] || "");
    }
    this.original = JSON.stringify(this.formWerte());
    this.meldung("");
  },

  meldung(text, art = "") {
    const el = $("#k-meldung");
    el.textContent = text;
    el.className = art;
  },

  leer() {
    this.aktuell = null;
    this.setzeForm({ anrede: "Herr" });
    this.markieren();
  },

  istGeaendert() {
    return JSON.stringify(this.formWerte()) !== this.original;
  },

  async verlassen() {
    if (!this.istGeaendert()) return true;
    const w = this.formWerte();
    if (!this.aktuell && !Object.entries(w).some(([k, v]) => k !== "anrede" && v)) return true;
    const a = await speichernFrage("Änderungen am Kontakt speichern?");
    if (a === "abbrechen") return false;
    if (a === "speichern") return this.speichern();
    this.verwerfen();
    return true;
  },

  async speichern() {
    const w = this.formWerte();
    let k;
    try {
      k = await py("kontakt_speichern", { werte: { ...w, id: this.aktuell || "" } });
    } catch (err) {
      if (!(err instanceof Hinweis)) throw err;
      this.meldung(err.message, "fehler");
      if (err.message.includes("E-Mail")) this.felder.email.focus();
      return false;
    }
    this.aktuell = k.id;
    await kontakteGeaendert();
    this.setzeForm(k);
    this.markieren();
    this.meldung(`Gespeichert: ${k.vorname} ${k.nachname}`.trim(), "ok");
    return true;
  },

  verwerfen() {
    const k = zustand.kontakte.find((c) => c.id === this.aktuell);
    if (k) this.setzeForm(k);
    else this.leer();
  },

  async neu() {
    if (!(await this.verlassen())) return;
    this.leer();
    this.felder.vorname.focus();
  },

  async waehlen(id) {
    if (id === this.aktuell || !(await this.verlassen())) return;
    const k = zustand.kontakte.find((c) => c.id === id);
    if (!k) return;
    this.aktuell = id;
    this.setzeForm(k);
    this.markieren();
  },

  markieren() {
    for (const tr of $$("#k-liste tbody tr")) tr.classList.toggle("gewaehlt", tr.dataset.id === this.aktuell);
  },

  liste() {
    const filt = klein($("#k-filter").value.trim());
    const zeilen = [];
    for (const k of zustand.kontakte) {
      if (filt && !klein(Object.values(k).join(" ")).includes(filt)) continue;
      const tr = h("tr", { dataset: { id: k.id } }, h("td", { text: anzeigeName(k) }), h("td", { text: k.dienstgrad }),
        h("td", { text: k.email }), h("td", { text: k.ort }));
      tr.addEventListener("click", sicher(() => this.waehlen(k.id)));
      zeilen.push(tr);
    }
    $("#k-liste tbody").replaceChildren(...zeilen);
    const n = zustand.kontakte.length;
    $("#k-anzahl").textContent = `${n} Kontakt${n !== 1 ? "e" : ""}`;
    this.markieren();
  },

  async loeschen() {
    const k = zustand.kontakte.find((c) => c.id === this.aktuell);
    if (!k || !(await frage(`${k.vorname} ${k.nachname} wirklich löschen?`.replace(/\s+/g, " "), "Kontakt löschen"))) return;
    await py("kontakt_loeschen", { id: k.id });
    this.leer();
    await kontakteGeaendert();
  },

  async importieren() {
    if (!(await this.verlassen())) return;
    const datei = await dateiWaehlen(".csv,.txt,.xlsx,.xlsm");
    if (!datei) return;
    const t = await py("tabelle_lesen", { pfad: await hochladen(datei) });
    const r = await this.importDialog(t, datei.name);
    if (!r) return;
    await kontakteGeaendert();
    let text = `${r.neu} Kontakt${r.neu !== 1 ? "e" : ""} importiert.`;
    if (r.uebersprungen) text += `\n${r.uebersprungen} übersprungen (bereits vorhanden: gleicher Name oder gleiche E-Mail).`;
    await meldung("Import abgeschlossen", text);
  },

  importDialog(t, dateiname) {
    const auswahl = {};
    const vorschau = h("tbody");
    const anzahl = h("p", { class: "hinweis" });
    const zuordnung = () => Object.fromEntries(Object.entries(auswahl).map(([k, s]) => [k, s.value === "" ? null : Number(s.value)]));
    const aktualisieren = sicher(async () => {
      const v = await py("import_vorschau", { kopf: t.kopf, zeilen: t.zeilen, zuordnung: zuordnung() });
      vorschau.replaceChildren(...v.kontakte.map((c) => h("tr", {}, h("td", { text: c.anrede }), h("td", { text: c.dienstgrad }),
        h("td", { text: `${c.vorname} ${c.nachname}` }),
        h("td", { text: [c.strasse, `${c.plz} ${c.ort}`.trim()].filter(Boolean).join(", ") }), h("td", { text: c.email }))));
      anzahl.textContent = `${v.anzahl} Kontakte werden übernommen.` + (v.ohne_mail ? ` ${v.ohne_mail} davon ohne E-Mail-Adresse.` : "");
    });
    const raster = h("div", { class: "zuordnung" }, info.zielfelder.map(([key, label]) => {
      const sel = h("select", { "aria-label": label }, h("option", { value: "", text: "– nicht verwenden –" }),
        t.kopf.map((k, i) => h("option", { value: String(i), text: k })));
      sel.value = t.zuordnung[key] == null ? "" : String(t.zuordnung[key]);
      sel.addEventListener("change", aktualisieren);
      auswahl[key] = sel;
      return [h("span", { text: label }), sel];
    }));
    aktualisieren();
    return dialog({
      titel: `${dateiname}: ${t.zeilen.length} Zeilen gefunden`, klasse: "breit",
      inhalt: h("div", {}, h("p", { class: "hinweis", text: "Bitte prüfen, welche Spalte zu welchem Feld gehört:" }), raster,
        h("h3", { text: "Vorschau (erste Einträge)" }),
        h("div", { class: "tabelle-rahmen" }, h("table", { class: "liste kompakt" },
          h("thead", {}, h("tr", {}, ["Anrede", "Dienstgrad", "Name", "Anschrift", "E-Mail"].map((s) => h("th", { text: s })))),
          vorschau)),
        anzahl),
      knoepfe: [{ text: "Abbrechen", wert: null },
        { text: "Importieren", art: "primaer", aktion: async (schliessen) => {
          schliessen(await py("kontakte_importieren", { kopf: t.kopf, zeilen: t.zeilen, zuordnung: zuordnung() }));
        } }],
    });
  },
};

// ============================================================================ Vorlage
const Vorlage = {
  felder: {},
  bilder: {},
  fokus: null,
  snapshot: null,
  platzhalter: null,

  init() {
    const formular = $("#vl-formular");
    for (const [titel, felder] of info.abschnitte) {
      const box = h("fieldset", { class: "box" }, h("legend", { text: titel }));
      for (const [key, label, art, hoehe, hinweis] of felder) {
        if (art === "bild") {
          box.append(this.bildZeile(key));
          continue;
        }
        let el;
        if (art === "schrift") el = h("select", {}, info.schriften.map((s) => h("option", { value: s, text: s })));
        else if (art === "text") el = h("textarea", { rows: hoehe, spellcheck: "true" });
        else el = h("input", { autocomplete: "off" });
        el.id = `vl-${key}`;
        if (art !== "schrift") el.addEventListener("focus", () => { this.fokus = el; });
        this.felder[key] = el;
        const zeile = h("div", { class: "vl-feld" }, h("label", { for: el.id, text: label }), el,
          hinweis ? h("div", { class: "hinweis", text: hinweis }) : null);
        if (key === "dateiname") {
          this.beispielEl = h("div", { class: "hinweis" });
          zeile.append(this.beispielEl);
          el.addEventListener("input", entprellt(() => this.beispiel().catch(zeigeFehler), 200));
        }
        box.append(zeile);
      }
      formular.append(box);
    }
    const tbody = $("#vl-platzhalter tbody");
    for (const [platzhalter, bedeutung] of info.platzhalter) {
      const tr = h("tr", {}, h("td", { text: platzhalter }), h("td", { text: bedeutung }));
      tr.addEventListener("click", () => {
        for (const x of $$("tr", tbody)) x.classList.toggle("gewaehlt", x === tr);
        this.platzhalter = platzhalter;
      });
      tr.addEventListener("mousedown", (e) => e.preventDefault()); // Fokus im Textfeld lassen
      tr.addEventListener("dblclick", () => this.einfuegen(platzhalter));
      tbody.append(tr);
    }
    $("#vl-einfuegen").addEventListener("mousedown", (e) => e.preventDefault());
    $("#vl-einfuegen").addEventListener("click", () => {
      if (this.platzhalter) this.einfuegen(this.platzhalter);
    });
    $("#vl-speichern").addEventListener("click", sicher(() => this.speichern()));
    $("#vl-vorschau").addEventListener("click", sicher(() => this.vorschau()));
    $("#vl-verwerfen").addEventListener("click", sicher(async () => {
      await this.laden();
      this.status("Änderungen verworfen.", "hinweis");
    }));
    $("#vl-export").addEventListener("click", sicher(() => this.exportieren()));
    $("#vl-import").addEventListener("click", sicher(() => this.importieren()));
    $("#vl-standard").addEventListener("click", sicher(() => this.standard()));
  },

  bildZeile(slot) {
    const bild = h("div", { class: "bild", text: "(kein Bild)" });
    const masse = {};
    const masseEl = h("div", { class: "masse" }, info.bild_masse[slot].map(([key, label]) => {
      masse[key] = h("input", { class: "mass", inputmode: "decimal", "aria-label": `${info.bild_titel[slot]} ${label}` });
      return h("label", {}, label, masse[key]);
    }), h("span", { class: "hinweis", text: "mm" }));
    this.bilder[slot] = { datei: "", bild, masse };
    return h("div", { class: "bildzeile" },
      h("div", { class: "titel", text: info.bild_titel[slot] }), bild,
      h("div", {}, h("button", { type: "button", onclick: sicher(() => this.bildWaehlen(slot)) }, "Bild wählen …"), " ",
        h("button", { type: "button", onclick: () => this.bildSetzen(slot, "", null) }, "Entfernen")),
      masseEl);
  },

  bildSetzen(slot, datei, dataUrl) {
    const b = this.bilder[slot];
    b.datei = datei;
    b.bild.replaceChildren(dataUrl ? h("img", { src: dataUrl, alt: info.bild_titel[slot] }) : "(kein Bild)");
  },

  roh() {
    const formular = Object.fromEntries(Object.entries(this.felder).filter(([k]) => k !== "schrift").map(([k, el]) => [k, el.value]));
    for (const [slot, b] of Object.entries(this.bilder)) {
      formular[slot] = { datei: b.datei, ...Object.fromEntries(Object.entries(b.masse).map(([k, el]) => [k, el.value])) };
    }
    return { formular, schrift: this.felder.schrift.value };
  },

  setze(v) {
    for (const [k, el] of Object.entries(this.felder)) {
      if (k !== "schrift") el.value = v.formular[k] ?? "";
    }
    this.felder.schrift.value = v.schrift;
    for (const [slot, b] of Object.entries(this.bilder)) {
      for (const [k, el] of Object.entries(b.masse)) el.value = v.formular[slot][k] ?? "";
      this.bildSetzen(slot, v.formular[slot].datei, v.bilder[slot]);
    }
    this.snapshot = JSON.stringify(this.roh());
    this.status("");
    return this.beispiel();
  },

  async laden() {
    await this.setze(await py("vorlage"));
  },

  istGeaendert() {
    return this.snapshot !== null && JSON.stringify(this.roh()) !== this.snapshot;
  },

  async verlassen() {
    if (!this.istGeaendert()) return true;
    const a = await speichernFrage("Die Vorlage wurde geändert. Änderungen speichern?");
    if (a === "abbrechen") return false;
    if (a === "speichern") return this.speichern();
    await this.laden();
    return true;
  },

  status(text, art = "hinweis") {
    const el = $("#vl-status");
    el.textContent = text;
    el.className = art;
  },

  async beispiel() {
    this.beispielEl.textContent = `Beispiel: ${await py("dateiname_beispiel", { muster: this.felder.dateiname.value })}`;
  },

  async speichern() {
    let r;
    try {
      r = await py("vorlage_speichern", this.roh());
    } catch (err) {
      if (!(err instanceof Hinweis)) throw err;
      await meldung("Bitte prüfen", err.message);
      return false;
    }
    this.snapshot = JSON.stringify(this.roh());
    if (r.unbekannt.length) this.status(`Gespeichert. Achtung, unbekannte Platzhalter: ${r.unbekannt.join(", ")}`, "fehler");
    else this.status("Vorlage gespeichert.", "ok");
    return true;
  },

  async vorschau() {
    const r = await mitWarten("Vorschau wird erstellt …", () => py("vorschau", this.roh()));
    if (r.unbekannt.length) this.status(`Unbekannte Platzhalter: ${r.unbekannt.join(", ")}`, "fehler");
    await pdfAnsehen(r.pfad, r.name, "Vorschau");
  },

  async bildWaehlen(slot) {
    const datei = await dateiWaehlen("image/png,image/jpeg,.png,.jpg,.jpeg");
    if (!datei) return;
    const r = await py("bild_uebernehmen", { slot, pfad: await hochladen(datei) });
    this.bildSetzen(slot, r.datei, r.bild);
    this.status("Bild übernommen – bitte speichern.", "info");
  },

  einfuegen(platzhalter) {
    const el = this.fokus;
    if (!el) {
      meldung("Platzhalter", "Bitte zuerst in das Feld klicken, in das der Platzhalter eingefügt werden soll.");
      return;
    }
    el.focus();
    el.setRangeText(platzhalter, el.selectionStart, el.selectionEnd, "end");
    el.dispatchEvent(new Event("input", { bubbles: true }));
  },

  async exportieren() {
    if (this.istGeaendert() && !(await this.verlassen())) return;
    const r = await py("vorlage_exportieren");
    await herunterladen(r.pfad, r.name);
    await meldung("Export", "Vorlage samt Bildern gespeichert. Die Datei lässt sich in der Desktop-App oder in einem "
      + "anderen Browser über „Vorlage importieren“ einlesen.\n\nHinweis: Sie enthält die Unterschrift – bitte nur vertraulich weitergeben.");
  },

  async importieren() {
    const datei = await dateiWaehlen(".einsatzvorlage,.json");
    if (!datei) return;
    if (!(await frage("Die aktuelle Vorlage wird ersetzt. Fortfahren?", "Vorlage importieren"))) return;
    await this.setze(await py("vorlage_importieren", { pfad: await hochladen(datei) }));
    this.status("Vorlage importiert.", "ok");
  },

  async standard() {
    if (!(await frage("Alle Texte auf die Beispielvorlage „Löschzug 1, Feuerwehr Musterstadt“ zurücksetzen? Bilder und "
      + "Positionen bleiben erhalten.\n\nTipp: Die eigene Vorlage vorher über „Vorlage exportieren“ sichern.", "Standardtexte"))) return;
    for (const [k, text] of Object.entries(info.standardtexte)) if (this.felder[k]) this.felder[k].value = text;
    await this.beispiel();
    this.status("Standardtexte eingesetzt – bitte speichern.", "info");
  },
};

// ============================================================================ Einstellungen
const Einstellungen = {
  SCHLUESSEL: "einsatzbescheinigung.letzteSicherung",

  init() {
    this.werteSetzen();
    const speichern = sicher(() => this.speichern());
    $("#s-bcc").addEventListener("input", entprellt(speichern, 400));
    $("#s-mails").addEventListener("change", speichern);
    $("#s-sammel").addEventListener("change", speichern);
    $("#s-sicherung").addEventListener("click", sicher(() => this.sichern()));
    $("#s-laden").addEventListener("click", sicher(() => this.einspielen()));
    $("#s-lizenzen").addEventListener("click", sicher(() => this.lizenzen()));
    $(".fuss .version").textContent = VERSION;
  },

  werteSetzen() {
    $("#s-bcc").value = zustand.einstellungen.bcc;
    $("#s-mails").checked = zustand.einstellungen.mails_erstellen;
    $("#s-sammel").checked = zustand.einstellungen.sammel_pdf;
  },

  async speichern() {
    const werte = { bcc: $("#s-bcc").value, mails_erstellen: $("#s-mails").checked, sammel_pdf: $("#s-sammel").checked };
    const r = await py("einstellungen_speichern", werte);
    zustand.einstellungen = { ...werte, bcc: werte.bcc.trim() };
    const el = $("#s-bcc-info");
    el.textContent = r.falsch.length ? `Ungültige Adresse: ${r.falsch.join(", ")}` : "Optional. Mehrere Adressen mit Komma trennen.";
    el.className = r.falsch.length ? "fehler" : "hinweis";
  },

  letzteSicherung() {
    try {
      return Number(localStorage.getItem(this.SCHLUESSEL)) || 0;
    } catch {
      return 0;
    }
  },

  async speicherAnzeigen() {
    const s = await py("speicherbedarf");
    let dauerhaft = "";
    try {
      dauerhaft = (await navigator.storage?.persisted?.())
        ? " Der Browser hält die Daten dauerhaft vor."
        : " Der Browser darf die Daten bei Speicherknappheit löschen – deshalb besonders an die Datensicherung denken.";
    } catch { /* ohne Storage-API */ }
    const zuletzt = this.letzteSicherung();
    $("#s-speicher").textContent = `Gespeichert: ${s.kontakte} Kontakt${s.kontakte !== 1 ? "e" : ""}, `
      + `${s.einsaetze} ${s.einsaetze === 1 ? "Einsatz" : "Einsätze"}, `
      + `${(s.bytes / 1e6).toLocaleString("de-DE", { maximumFractionDigits: 1 })} MB.`
      + ` Letzte Datensicherung: ${zuletzt ? new Date(zuletzt).toLocaleString("de-DE") : "noch keine"}.${dauerhaft}`;
  },

  async sichern() {
    const r = await mitWarten("Datensicherung wird erstellt …", () => py("datensicherung"));
    await herunterladen(r.pfad, r.name);
    try {
      localStorage.setItem(this.SCHLUESSEL, String(Date.now()));
    } catch { /* ohne localStorage */ }
    await this.speicherAnzeigen();
  },

  async einspielen() {
    const datei = await dateiWaehlen(".zip,application/zip");
    if (!datei) return;
    if (!(await frage("Alle Daten in diesem Browser (Kontakte, Vorlage, Einstellungen und gespeicherte Einsätze) werden "
      + "durch die Datensicherung ersetzt. Fortfahren?", "Datensicherung einspielen"))) return;
    const r = await mitWarten("Datensicherung wird eingespielt …", async () => py("datensicherung_laden", { pfad: await hochladen(datei) }));
    zustand.kontakte = r.kontakte;
    zustand.einstellungen = r.einstellungen;
    this.werteSetzen();
    Kontakte.leer();
    Kontakte.liste();
    Einsatz.neu();
    await Vorlage.laden();
    await Verlauf.aktualisieren();
    await this.speicherAnzeigen();
    const wann = r.erstellt ? ` vom ${new Date(r.erstellt).toLocaleString("de-DE")}` : "";
    await meldung("Datensicherung eingespielt", `Die Datensicherung${wann} wurde eingespielt.`);
  },

  async lizenzen() {
    const text = await py("lizenzen");
    await dialog({ titel: "Lizenzen", klasse: "breit", inhalt: h("pre", { class: "lizenzen", text }) });
  },
};
// ============================================================================ Start
function ladeFehler(text, details = "") {
  const laden = $("#laden");
  laden.replaceChildren(h("div", { class: "laden-fehler" }, h("h2", { text: "Die Einsatzbescheinigung kann nicht starten" }),
    h("p", { class: "dlg-text", text }), details ? h("pre", { class: "details", text: details }) : null));
  laden.hidden = false;
}

async function einzigerTab() {
  if (!navigator.locks) return true;
  return new Promise((ok) => {
    navigator.locks.request("einsatzbescheinigung", { ifAvailable: true }, (lock) => {
      ok(Boolean(lock));
      return lock ? new Promise(() => {}) : undefined; // Sperre halten, solange die Seite offen ist
    }).catch(() => ok(true));
  });
}

async function starten() {
  if (!(await einzigerTab())) {
    ladeFehler("Die Einsatzbescheinigung ist bereits in einem anderen Tab oder Fenster geöffnet. Bitte dort weiterarbeiten "
      + "(oder den anderen Tab schließen und diese Seite neu laden) – sonst könnten sich Änderungen gegenseitig überschreiben.");
    return;
  }
  navigator.storage?.persist?.().catch(() => {});
  try {
    worker = new Worker(`worker.js?v=${VERSION}`, { type: "module" });
  } catch (err) {
    ladeFehler("Dieser Browser ist zu alt. Bitte einen aktuellen Browser verwenden (Edge, Chrome, Firefox oder Safari).", String(err));
    return;
  }
  worker.addEventListener("message", antwort);
  worker.addEventListener("error", (e) => {
    ladeFehler("Das Programm konnte nicht geladen werden. Bitte die Seite neu laden; hilft das nicht, einen aktuellen Browser "
      + "(Edge, Chrome, Firefox oder Safari) verwenden.", e.message || "");
  });
  try {
    info = await senden({ art: "start" });
  } catch (err) {
    ladeFehler("Beim Laden ist ein Fehler aufgetreten. Bitte die Seite neu laden.", String(err.message || err));
    return;
  }
  zustand.kontakte = info.kontakte;
  zustand.einstellungen = info.einstellungen;

  for (const b of $$(".reiter button")) b.addEventListener("click", sicher(() => zeigeSeite(b.dataset.seite)));
  Einsatz.init();
  Verlauf.init();
  Kontakte.init();
  Vorlage.init();
  Einstellungen.init();
  await Vorlage.laden();
  await Einsatz.pruefen();
  window.addEventListener("beforeunload", (e) => {
    if (Kontakte.istGeaendert() || Vorlage.istGeaendert()) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  $("#laden").hidden = true;
  $("#app").hidden = false;
  document.body.dataset.bereit = "1";
  Einsatz.feld.nummer.focus();
}

starten().catch((err) => ladeFehler("Beim Starten ist ein Fehler aufgetreten.", String(err && err.stack ? err.stack : err)));
