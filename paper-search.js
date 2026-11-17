const search = document.querySelector("[data-paper-search]");
const input = search.querySelector("input");
const status = search.querySelector("[role=status]");
const papers = Array.from(document.querySelectorAll(".paper"), (article) => ({
  article,
  text: article.textContent.toLocaleLowerCase()
}));

function filterPapers() {
  const words = input.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  let matches = 0;

  for (const { article, text } of papers) {
    const matched = words.every((word) => text.includes(word));
    article.hidden = !matched;
    matches += Number(matched);
  }

  status.textContent = matches === 0
    ? "没有匹配的论文。试试其他关键词。"
    : `显示 ${matches} / ${papers.length} 篇论文`;
}

input.addEventListener("input", filterPapers);
filterPapers();
search.hidden = false;
