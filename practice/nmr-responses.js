"use strict";

const samplePicker = document.getElementById("answer-sample");
const answerView = document.getElementById("answer-view");
const answerRows = document.getElementById("answer-rows");
const answerStatus = document.getElementById("answer-status");
const models = ["deepseek-v4-pro", "kimi-3.1-pro", "GLM-5.3"];
const samples = Array.from(samplePicker.options, option => option.value);
const csvUrl = new URL("resources/nmr-shift-prediction/answers/all-predictions.csv", document.baseURI);

function parseAnswers(csv) {
  const lines = csv.trimEnd().split(/\r?\n/);
  const header = "model,sample_id,nucleus,site_id,point_ppm,lower95_ppm,upper95_ppm";
  if (lines.shift() !== header || lines.length !== samples.length * 8 * models.length) {
    throw new Error("Unexpected answer CSV");
  }

  const answers = new Map(samples.map(sample => [sample, new Map()]));
  for (const line of lines) {
    const fields = line.split(",");
    const [model, sample, nucleus, site, point, lower, upper] = fields;
    if (fields.length !== 7 || !models.includes(model) || !answers.has(sample)
        || !["1H", "13C"].includes(nucleus) || !site
        || ![point, lower, upper].every(number => number && Number.isFinite(Number(number)))
        || Number(lower) > Number(point) || Number(point) > Number(upper)) {
      throw new Error("Malformed answer row");
    }
    const sites = answers.get(sample);
    const key = nucleus + "/" + site;
    if (!sites.has(key)) {
      sites.set(key, {nucleus, site, predictions: new Map()});
    }
    const {predictions} = sites.get(key);
    if (predictions.has(model)) {
      throw new Error("Duplicate prediction");
    }
    predictions.set(model, {point, lower, upper});
  }

  for (const sites of answers.values()) {
    if (sites.size !== 8 || Array.from(sites.values()).some(site => site.predictions.size !== models.length)) {
      throw new Error("Missing predictions");
    }
  }
  return answers;
}

function renderSample(answers) {
  const sample = samplePicker.value;
  const rows = Array.from(answers.get(sample).values(), ({site, predictions}) => {
    const row = document.createElement("tr");
    const heading = document.createElement("th");
    heading.scope = "row";
    heading.textContent = site;
    row.append(heading);
    for (const model of models) {
      const {point, lower, upper} = predictions.get(model);
      const cell = document.createElement("td");
      const estimate = document.createElement("strong");
      const interval = document.createElement("small");
      estimate.textContent = point;
      interval.textContent = "[" + lower + ", " + upper + "]";
      cell.append(estimate, interval);
      row.append(cell);
    }
    return row;
  });
  answerRows.replaceChildren(...rows);
  answerStatus.textContent = sample + " · 8 个位点"
    + (sample === "T19" ? " · 三份答卷均来自统一格式重跑" : "");
}

fetch(csvUrl)
  .then(response => {
    if (!response.ok) throw new Error("Answer CSV unavailable");
    return response.text();
  })
  .then(parseAnswers)
  .then(answers => {
    samplePicker.disabled = false;
    answerView.hidden = false;
    renderSample(answers);
    samplePicker.addEventListener("change", () => renderSample(answers));
  })
  .catch(() => {
    answerStatus.textContent = "答卷预览暂时无法加载，可直接下载 CSV。";
  });
