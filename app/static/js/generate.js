document.addEventListener("DOMContentLoaded", function () {
  console.log("Generate.js loaded ✅");

  const uploadSourceBtn = document.getElementById("uploadSourceBtn");
  const sourceFileInput = document.getElementById("sourceImageUpload");
  const sourceImageGrid = document.getElementById("sourceImageGrid");
  const sourceImageContainer = document.getElementById("sourceImageContainer");
  const generateBtn = document.querySelector(".control__panel-generate");

  const deepfakeImage = document.getElementById("deepfakeImage");
  const cameraFeed = document.getElementById("cameraFeed");
  const parametersInfo = document.getElementById("parametersInfo");

  window.selectedSourceInput = null;
  let isGenerating = false;
  let genController = null;
  let genLoopRunning = false;

// ---------------------------------------------------------------------------
// Token log + metrics panel setup (same structure as Detect.js)
// ---------------------------------------------------------------------------
function mmss(secs){
  secs = Math.max(0, Math.floor(secs || 0));
  const m = Math.floor(secs/60), s = secs % 60;
  return `${m}:${s.toString().padStart(2,'0')}`;
}

function ensureParamSubpanels() {
  if (!document.getElementById("tokenLogDiv") || !document.getElementById("metricsDiv")) {
    const html = `
      <div id="tokenLogDiv" style="font-family:ui-monospace,Menlo,monospace;font-size:12px;"></div>
      <div id="metricsDiv"   style="margin-top:8px;"></div>
    `;
    parametersInfo.innerHTML = html;
  }
}

// create initial placeholders
ensureParamSubpanels();
document.getElementById("metricsDiv").innerHTML = `<p>Waiting for data...</p>`;

// ---------------------------------------------------------------------------
// Refresh the quota table (calls /quota_debug)
// ---------------------------------------------------------------------------
async function refreshTokenPanel(){
  ensureParamSubpanels();
  const tokenLogDiv = document.getElementById("tokenLogDiv");

  try{
    const r = await fetch("/quota_debug", { credentials:"same-origin", cache:"no-cache" });
    if (!r.ok) throw new Error(r.status);
    const j  = await r.json();

    const cfg = j.config || {};
    const dd  = j.deepfake_detect || {};
    const fs  = j.face_swap || {};

    const rows = [
      ["Service", "Used", "Remaining", "Window resets", "Stream left"],
      ["Detect (webcam)",
        dd.uses ?? 0,
        (cfg.FREE_USES ?? 0) - (dd.uses ?? 0),
        mmss(dd.window_seconds_left ?? 0),
        mmss(dd.stream_seconds_left ?? 0)
      ],
      ["Generate (face swap)",
        fs.uses ?? 0,
        (cfg.FREE_USES ?? 0) - (fs.uses ?? 0),
        mmss(fs.window_seconds_left ?? 0),
        mmss(fs.stream_seconds_left ?? 0)
      ],
    ];

    const table = `
      <table style="border-collapse:collapse;width:100%">
        ${rows.map((row,i)=>`
          <tr>
            ${row.map((cell,idx)=>`
              <td style="
                border:1px solid #333;padding:6px 8px;
                ${i===0?'font-weight:700;background:#111;color:#ddd;':''}
                text-align:${idx===0?'left':'center'};">
                ${cell}
              </td>`).join("")}
          </tr>`).join("")}
      </table>
    `;
    tokenLogDiv.innerHTML = table;
  }catch(e){
    tokenLogDiv.innerHTML = `<div style="color:#c33">quota_debug unavailable (${e.message})</div>`;
  }
}

// poll every second
setInterval(refreshTokenPanel, 1000);
refreshTokenPanel();


  // ----------------------------------------------------------
  // SOURCE UPLOAD
  // ----------------------------------------------------------
  if (uploadSourceBtn && sourceFileInput) {
    uploadSourceBtn.addEventListener("click", () => sourceFileInput.click());

    sourceFileInput.addEventListener("change", function (event) {
      handleImageUpload(event, sourceImageGrid, sourceImageContainer, "source");
      const file = event.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = function (e) {
          window.selectedSourceInput = e.target.result;
          console.log("[GEN] selected source length:", window.selectedSourceInput.length);
        };
        reader.readAsDataURL(file);
      }
    });
  }

  // ----------------------------------------------------------
  // CAPTURE FRAME FROM WEBCAM (optimized for speed)
  // ----------------------------------------------------------
  function captureWebcamFrame(videoElement) {
    if (!videoElement) return null;
    if (videoElement.readyState < 2) return null;
    if (videoElement.paused) { try { videoElement.play(); } catch {} return null; }

    const canvas = document.createElement("canvas");
    const maxW = 480; // higher res than before, better quality
    const vw = videoElement.videoWidth  || maxW;
    const vh = videoElement.videoHeight || Math.round(maxW * 9 / 16);
    const scale = Math.min(1, maxW / vw);
    canvas.width  = Math.round(vw * scale);
    canvas.height = Math.round(vh * scale);

    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.75); // slightly higher quality
  }

  // ----------------------------------------------------------
  // GENERATION LOOP
  // ----------------------------------------------------------
  async function generateDeepfakeLoop(signal) {
    console.log("[GEN] loop started");
    while (isGenerating) {
      const targetImage = captureWebcamFrame(cameraFeed);
      if (!targetImage) {
        await new Promise(r => setTimeout(r, 50));
        continue;
      }

      try {
        const response = await fetch("/generate_deepfake", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          cache: "no-cache",
          signal,
          body: JSON.stringify({
            source: "webcam",
            action: "frame",
            target_img: targetImage,
          }),
        });

        console.log("[GEN] frame status:", response.status);

// ---- handle quota/auth/session-expired
let shouldStop = false;
let reason = "";

if ([440, 429, 401].includes(response.status) || response.redirected) {
  shouldStop = true;
  reason =
    response.status === 440 ? "⏰ Session expired — please restart generation." :
    response.status === 429 ? "⚠️ Free quota reached." :
    "🔐 Login required.";
} else {
  try {
    const peek = await response.clone().json();
    if (peek?.error === "stream_session_expired") {
      shouldStop = true;
      reason = "⏰ Session expired — please restart generation.";
    }
  } catch {}
}

if (shouldStop) {
  ensureParamSubpanels();
  document.getElementById("metricsDiv").innerHTML = reason;
  isGenerating = false;

  if (genController) genController.abort();
  generateBtn.textContent = "Generate Deepfake";
  generateBtn.classList.remove("active");
  restoreVideo();

  try { await refreshTokenPanel(); } catch {}
  try {
    await fetch("/generate_deepfake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ source: "webcam", action: "stop" }),
    });
  } catch {}
  break;
}


        let data;
        try { data = await response.json(); }
        catch (e) {
          const text = await response.text();
          console.warn("Non-JSON from server:", response.status, text.slice(0, 200));
          await new Promise(r => setTimeout(r, 80));
          continue;
        }

        if (data.deepfake_image) {
          deepfakeImage.src = data.deepfake_image;
          deepfakeImage.style.display = "block";
          hideVideo();

          ensureParamSubpanels();
document.getElementById("metricsDiv").innerHTML = `
  <div style="text-align:left;">
    <b>FPS:</b> ${Number(data.fps || 0).toFixed(2)}<br>
    <b>Distance:</b> ${data.distance != null ? Number(data.distance).toFixed(4) : "—"}<br>
  </div>
`;

        } else {
          restoreVideo();
          deepfakeImage.style.display = "none";
          ensureParamSubpanels();
            document.getElementById("metricsDiv").innerHTML = "Waiting for data...";

        }

        // adaptive delay based on FPS for smoother realtime
        const delay = Math.max(0, Math.min(50, 1000 / (data?.fps || 10) - 20));
        await new Promise(r => setTimeout(r, delay));

      } catch (error) {
        if (error.name === "AbortError") break;
        console.error("Error generating deepfake:", error);
        restoreVideo();
        deepfakeImage.style.display = "none";
        ensureParamSubpanels();
document.getElementById("metricsDiv").innerHTML = "Error generating deepfake.";

      }
    }

    restoreVideo();
    deepfakeImage.style.display = "none";
    console.log("[GEN] loop ended");
  }

  // ----------------------------------------------------------
  // BUTTON HANDLER
  // ----------------------------------------------------------
  generateBtn.addEventListener("click", async function () {
    // OFF → ON
    if (!isGenerating) {
      if (genLoopRunning) return;
      generateBtn.disabled = true;
      const originalText = generateBtn.textContent;
      generateBtn.textContent = "Starting…";

      if (!window.selectedSourceInput) {
        parametersInfo.innerHTML = "Select a source image first.";
        generateBtn.textContent = originalText;
        generateBtn.disabled = false;
        return;
      }

      try {
        const r = await fetch("/generate_deepfake", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          cache: "no-cache",
          body: JSON.stringify({
            source: "webcam",
            action: "start",
            source_img: window.selectedSourceInput,
          }),
        });

        if (r.status === 429) {
          parametersInfo.innerHTML = "Free quota reached.";
          generateBtn.textContent = originalText;
          generateBtn.disabled = false;
          return;
        }
        if (r.status === 401 || r.redirected) {
          parametersInfo.innerHTML = "Login required.";
          generateBtn.textContent = originalText;
          generateBtn.disabled = false;
          return;
        }
        if (!r.ok) {
          parametersInfo.innerHTML = `Server error (${r.status}) starting generation.`;
          generateBtn.textContent = originalText;
          generateBtn.disabled = false;
          return;
        }
      } catch (e) {
        parametersInfo.innerHTML = "Network error starting generation.";
        generateBtn.textContent = originalText;
        generateBtn.disabled = false;
        return;
      }

        await refreshTokenPanel();

      // Start loop
      isGenerating = true;
      genLoopRunning = true;
      genController = new AbortController();
      generateBtn.textContent = "Stop Generating";
      generateBtn.disabled = false;

      generateDeepfakeLoop(genController.signal).finally(() => {
        isGenerating = false;
        genLoopRunning = false;
        genController = null;
        generateBtn.textContent = "Generate Deepfake";
        restoreVideo();
      });
      return;
    }

    // ON → OFF
    isGenerating = false;
    if (genController) genController.abort();
    restoreVideo();
    deepfakeImage.style.display = "none";
    parametersInfo.innerHTML = "Waiting for data...";
    generateBtn.textContent = "Generate Deepfake";
    generateBtn.classList.remove("active");

    try {
  await fetch("/generate_deepfake", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ source: "webcam", action: "stop" }),
  });
} catch (e) {}
await refreshTokenPanel();  // ✅ Update table after STOP


  });

  // ----------------------------------------------------------
  // VISUAL HELPERS
  // ----------------------------------------------------------
  function hideVideo() {
    cameraFeed.style.opacity = "0";
    cameraFeed.style.pointerEvents = "none";
  }
  function restoreVideo() {
    cameraFeed.style.opacity = "1";
    cameraFeed.style.pointerEvents = "auto";
  }

  window.toggleCollapse = function (id) {
    var content = document.getElementById(id);
    if (id === "sourceImageContainer") {
      if (sourceImageGrid.children.length > 0 && content.classList.contains("open")) return;
    }
    content.classList.toggle("open");
  };
});
