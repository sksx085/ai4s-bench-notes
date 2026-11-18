const movedSections = new Map([
  ["#demo-nmr", "./bench/nmr.html"],
  ["#demo-lanthanides", "./bench/lanthanides.html"],
  ["#demo-catalysis", "./bench/catalysis.html"],
  ["#daily-practice", "./practice/index.html"],
  ["#practice-2026-11-17", "./practice/nmr-shift-prediction.html"],
  ["#authoring-ideas", "./practice/ideas.html"],
  ["#evidence-note", "./bench/notes.html#evidence-note"]
]);

function followMovedSection() {
  const movedPage = movedSections.get(location.hash);
  if (movedPage) {
    location.replace(movedPage);
  }
}

followMovedSection();
window.addEventListener("hashchange", followMovedSection);
