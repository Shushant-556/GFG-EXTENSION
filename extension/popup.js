
const $ = id => document.getElementById(id);

async function cfg() {
  return chrome.storage.local.get({
    backend: "http://127.0.0.1:8000",
    apiKey: ""
  });
}

// Escape HTML before displaying AI-generated content.
function esc(s) {
  const map = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  };

  return String(s ?? "").replace(/[&<>"']/g, c => map[c]);
}

// Capture GFG problem.
$("capture").onclick = async () => {
  $("status").textContent = "Capturing visible page…";

  try {
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true
    });

    if (!tab || !tab.url?.includes("geeksforgeeks.org")) {
      throw Error("Open a GFG problem page first.");
    }

    const [x] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const body =
          document.querySelector("main")?.innerText ||
          document.body.innerText;

        const h =
          document.querySelector("h1")?.innerText ||
          document.title;

        const match = label => {
          const i = body.toLowerCase().indexOf(label.toLowerCase());
          return i < 0 ? "" : body.slice(i, i + 2500);
        };

        return {
          title: h,
          url: location.href,
          statement: body.slice(0, 16000),
          constraints: match("Constraints"),
          examples: match("Examples") || match("Example")
        };
      }
    });

    Object.entries(x.result).forEach(([k, v]) => {
      if ($(k)) $(k).value = v || "";
    });

    $("status").textContent =
      "Captured — inspect and correct before sending.";

  } catch (e) {
    $("status").textContent = "Capture error: " + e.message;
  }
};

// Generate solution, insert into Ace editor, submit to GFG.
$("solve").onclick = async () => {
  const c = await cfg();

  $("solve").disabled = true;
  $("status").textContent =
    "AI solving, validating and committing…";
  $("result").textContent = "";

  try {
    const backend = c.backend.replace(/\/+$/, "");

    const r = await fetch(backend + "/solve", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(c.apiKey ? { "X-Autosolver-Key": c.apiKey } : {})
      },
      body: JSON.stringify({
        title: $("title").value,
        url: $("url").value,
        statement: $("statement").value,
        constraints: $("constraints").value,
        examples: $("examples").value
      })
    });

    const d = await r.json();

    if (!r.ok) {
      throw Error(d.detail || r.statusText);
    }

    const solution = d.solution || {};
    const javaCode = solution.class_code;

    if (!javaCode) {
      throw Error("Backend returned no Java solution.");
    }

    console.log("FULL SOLUTION:", javaCode);
    console.log("SOLUTION OBJECT:", solution);

    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true
    });

    if (!tab || !tab.url?.includes("geeksforgeeks.org")) {
      throw Error("Please open a GFG problem page first.");
    }

    $("status").textContent =
      "Solution generated. Inserting into GFG editor…";

    // Execute inside the actual GFG page context.
    const [submission] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",

      func: async code => {
        const sleep = ms =>
          new Promise(resolve => setTimeout(resolve, ms));

        // Wait for Ace editor initialization.
        let editor = null;

        for (let i = 0; i < 30; i++) {
          const el = document.querySelector("#ace-editor");

          editor =
            el?.env?.editor ||
            window.ace?.edit?.("ace-editor");

          if (editor) break;

          await sleep(500);
        }

        if (!editor) {
          return "ERROR: Ace editor not found.";
        }

        // Insert code and normalize line endings.
        const normalize = text =>
          String(text).replace(/\r\n/g, "\n").replace(/\r/g, "\n");

        const expected = normalize(code).replace(/\n+$/, "");

        editor.setValue(code, -1);
        editor.clearSelection();
        editor.focus();

        // Retry if Ace did not retain the code.
        for (let i = 0; i < 5; i++) {
          if (normalize(editor.getValue()) === expected) break;

          editor.setValue(code, -1);
          editor.clearSelection();

          await sleep(300);
        }

        const actual = normalize(editor.getValue()).replace(/\n+$/, "");

        if (actual !== expected) {
          return "ERROR: Code insertion failed. Actual length: " +
            actual.length + ", expected length: " + expected.length;
        }

        // Confirm insertion.
        await sleep(1500);

        // Find Submit button.
        // Select GFG's actual problem submission button.
const submitButton =
  document.querySelector("button[class*='problems_submit_button']");

if (!submitButton) {
  return "ERROR: GFG problem Submit button not found.";
}

if (submitButton.disabled) {
  return "ERROR: GFG problem Submit button is disabled.";
}

        if (!submitButton) {
          return "ERROR: GFG Submit button not found.";
        }

        // Wait up to 15 seconds for GFG to enable Submit.
const enableStart = Date.now();

while (submitButton.disabled && Date.now() - enableStart < 15000) {
  await sleep(500);
}

if (submitButton.disabled) {
  return "ERROR: Submit remained disabled after 15 seconds.";
}

        // Snapshot existing text to avoid old verdicts.
        const previousText = document.body.innerText;

        // Trigger submission.
        submitButton.click();

        // Watch for a new verdict.
        const verdicts = [
          ["Accepted", /\baccepted\b/i],
          ["Wrong Answer", /\bwrong answer\b/i],
          ["Compilation Error", /\bcompilation error\b/i],
          ["Runtime Error", /\bruntime error\b/i],
          ["Time Limit Exceeded", /\btime limit exceeded\b/i],
          ["Memory Limit Exceeded", /\bmemory limit exceeded\b/i]
        ];

        const start = Date.now();

        while (Date.now() - start < 120000) {
          await sleep(2000);

          const currentText = document.body.innerText;

          const newText = currentText.startsWith(previousText)
            ? currentText.slice(previousText.length)
            : currentText;

          for (const [name, regex] of verdicts) {
            if (regex.test(newText)) {
              return "VERDICT: " + name;
            }
          }
        }

        return "SUBMITTED: Verdict not detected within 120 seconds.";
      },

      args: [javaCode]
    });

    const result = submission.result || "";

    if (result.startsWith("ERROR:")) {
      throw Error(result);
    }

    $("status").textContent = result;

    // GitHub links.
    const javaLink =
      solution.github_solution_url ||
      solution.solution_url ||
      d.github_solution_url ||
      "";

    const explanationLink =
      solution.github_explanation_url ||
      solution.explanation_url ||
      d.github_explanation_url ||
      "";

    // Solution explanation and complexity.
    const approach =
      solution.approach ||
      solution.explanation ||
      "No approach explanation returned.";

    const time =
      solution.time_complexity ||
      solution.timeComplexity ||
      "Not specified";

    const space =
      solution.space_complexity ||
      solution.spaceComplexity ||
      "Not specified";

    const signature =
      solution.signature_notes ||
      solution.signature ||
      "Use the required GFG function signature.";

    $("result").innerHTML = `
      <div class="solution-result">

        <h3>Solution Generated</h3>

        ${
          javaLink
            ? `<p>
                 <a href="${esc(javaLink)}" target="_blank">
                   View Java Solution on GitHub
                 </a>
               </p>`
            : ""
        }

        ${
          explanationLink
            ? `<p>
                 <a href="${esc(explanationLink)}" target="_blank">
                   View Explanation on GitHub
                 </a>
               </p>`
            : ""
        }

        <h4>Approach</h4>
        <pre>${esc(approach)}</pre>

        <h4>Complexity</h4>
        <p><b>Time:</b> ${esc(time)}</p>
        <p><b>Space:</b> ${esc(space)}</p>

        <h4>Signature Notes</h4>
        <pre>${esc(signature)}</pre>

      </div>
    `;

  } catch (e) {
    $("status").textContent = "Failed: " + e.message;
    console.error("AutoSolver error:", e);

  } finally {
    $("solve").disabled = false;
  }
};
