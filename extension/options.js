
const $ = id => document.getElementById(id);

chrome.storage.local.get({
  backend: "http://127.0.0.1:8000",
  apiKey: ""
}, v => {
  $("backend").value = v.backend;
  $("apiKey").value = v.apiKey;
});

$("save").onclick = () => chrome.storage.local.set({
  backend: $("backend").value.trim().replace(/\/$/, ""),
  apiKey: $("apiKey").value.trim()
}, () => {
  $("status").textContent = "Saved ✓";
});
