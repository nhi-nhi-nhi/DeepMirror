document.addEventListener("DOMContentLoaded", function () {
    console.log("Detect.js loaded");

    // Selecting elements
    const detectButton          = document.querySelector(".control__panel-detect");
    const cameraButton          = document.querySelector(".toggle-btn");
    const uploadDetectVideoBtn  = document.getElementById("uploadDetectVideoBtn");
    const detectFileInput       = document.getElementById("detectVideoUpload");
    const detectVideoGrid       = document.getElementById("detectVideoGrid");
    const detectVideoContainer  = document.getElementById("detectVideoContainer");
    const showVideoButton       = document.getElementById("showVideoButton");
    const statusInfo            = document.getElementById("statusInfo");
    const cameraFeed            = document.getElementById("cameraFeed");

    // OPTIONAL overlay if you want a <img> for annotated results
    const deepfakeImage     = document.getElementById("deepfakeImage"); 

    let selectedDetectVideo = null; 
    let isDetecting         = false; 
    let isCameraOn          = false;
    let cameraStream        = null;
    let detectController = null;    // AbortController for the current detect loop
    let detectLoopRunning = false;  // prevent multiple loops at once


    const parametersInfo = document.getElementById("parametersInfo");

    // -------------------------------------------------------------------------
    // DETECT BUTTON: toggles detection on/off, calls detect loop
    // -------------------------------------------------------------------------
    if (detectButton) {
      detectButton.addEventListener("click", async function () {
        this.classList.toggle("active");
        const eyeIconOn  = this.getAttribute("data-icon-on");
        const eyeIconOff = this.getAttribute("data-icon-off");

        if (this.classList.contains("active")) {
          // START
          this.innerHTML = `<img src="${eyeIconOn}" class="icon eye_icon_on"> Deepfake Detection: On`;
          if (detectLoopRunning) return;          // don’t start twice
          isDetecting = true;
          detectLoopRunning = true;
          detectController = new AbortController();
          updateDetectButtonUI();
          detectDeepfakeLoop(detectController.signal)
            .finally(() => {
              isDetecting = false;
              detectLoopRunning = false;
              detectController = null;
              updateDetectButtonUI();
            });
        } else {
          // STOP
          this.innerHTML = `<img src="${eyeIconOff}" class="icon eye_icon_off"> Deepfake Detection: Off`;
          isDetecting = false;
          if (detectController) detectController.abort();
          deepfakeImage.style.display = "none";
          statusInfo.innerHTML = "DeepFake Detection Turned Off";
          updateDetectButtonUI();

          // Tell backend to end the stream session now (so a new start consumes the next “use”)
          fetch("/predict_deepfake", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ source: "webcam", action: "stop" })
          }).catch(()=>{});
        }
      });
    }

    // -------------------------------------------------------------------------
    // SHOW VIDEO BUTTON: plays selected video (if any)
    // -------------------------------------------------------------------------
    if (showVideoButton) {
        showVideoButton.addEventListener("click", function () {
            if (selectedDetectVideo) {
                showVideoOnCameraFeed(selectedDetectVideo);
            } else {
                statusInfo.innerHTML = "No video selected.";
            }
        });
    }

    // -------------------------------------------------------------------------
    // FUNCTION: show uploaded/processed video in cameraFeed
    // -------------------------------------------------------------------------
    function showVideoOnCameraFeed(videoPath) {
        // Set the source of the video directly to the cameraFeed element
        cameraFeed.src = `/static/processed_videos/${videoPath.split('/')[3]}`;
        console.log("Video path:", cameraFeed.src);  // Log to verify path

        cameraFeed.style.display = "block";  // Make sure it's visible
        cameraFeed.style.visibility = "visible"; // Ensure visibility is on

        // Wait for the video to be ready to play
        cameraFeed.oncanplay = function () {
            console.log("Video is ready to play.");
        };
    }

    // -------------------------------------------------------------------------
    // VIDEO UPLOAD / SELECTION
    // -------------------------------------------------------------------------
    if (uploadDetectVideoBtn && detectFileInput) {
        uploadDetectVideoBtn.addEventListener("click", () => detectFileInput.click());

        detectFileInput.addEventListener("change", function (event) {
            handleVideoUpload(event, detectVideoGrid, detectVideoContainer, "detect");
        });
    }

    function handleVideoUpload(event, videoGrid, videoContainer, type) {
        const files = event.target.files;

        if (files.length > 0) {
            videoContainer.classList.add("open");
        }

        for (let file of files) {
            const videoURL    = URL.createObjectURL(file);
            const videoWrapper= document.createElement("div");
            videoWrapper.classList.add("video-wrapper");

            const videoElement= document.createElement("video");
            videoElement.src   = videoURL;
            videoElement.controls = true;
            videoElement.classList.add("uploaded-video");

            const radio       = document.createElement("input");
            radio.type        = "radio";
            radio.name        = type + "-video";
            radio.classList.add("video-radio");
            radio.id          = `video-${type}-${Math.random().toString(36).substr(2, 9)}`;

            const label       = document.createElement("label");
            label.setAttribute("for", radio.id);

            radio.addEventListener("change", function () {
                if (radio.checked) {
                    selectedDetectVideo = file;
                }
            });

            videoWrapper.appendChild(radio);
            videoWrapper.appendChild(label);
            videoWrapper.appendChild(videoElement);
            videoGrid.appendChild(videoWrapper);
        }
    }

    // -------------------------------------------------------------------------
    // CAPTURE A FRAME FROM THE WEBCAM
    // -------------------------------------------------------------------------
    function captureWebcamFrame(videoElement) {
        if (!videoElement || videoElement.readyState !== 4) {
            console.error("Webcam feed is not available or not ready yet.");
            return null;
        }
        const canvas = document.createElement("canvas");
        canvas.width  = videoElement.videoWidth;
        canvas.height = videoElement.videoHeight;
        const ctx     = canvas.getContext("2d");
        ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.6);
    }

    // -------------------------------------------------------------------------
    // START / STOP CAMERA
    // -------------------------------------------------------------------------
    async function startCamera() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            cameraStream = stream;
            cameraFeed.srcObject = stream;

            cameraFeed.style.display       = "block";
            cameraFeed.style.visibility    = "visible";

            isCameraOn = true;
            statusInfo.innerHTML = "Camera started successfully.";
            console.log("Camera stream started, isCameraOn =", isCameraOn);
        } catch (error) {
            console.error("Error accessing the camera:", error);
            statusInfo.innerHTML = "Error accessing the camera.";
        }
    }

    function stopCamera() {
        if (cameraStream) {
            cameraStream.getTracks().forEach(track => track.stop());
            cameraStream = null;
        }
        cameraFeed.srcObject = null;

        cameraFeed.style.display    = "none";
        cameraFeed.style.visibility = "hidden";

        isCameraOn = false;
        statusInfo.innerHTML = "Camera turned off.";
        console.log("Camera stream stopped, isCameraOn =", isCameraOn);
        // End stream server-side if user turns camera off
        fetch("/predict_deepfake", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ source: "webcam", action: "stop" })
        }).catch(()=>{});
    }

    function updateDetectButtonUI() {
        const eyeIconOn  = detectButton.getAttribute("data-icon-on");
        const eyeIconOff = detectButton.getAttribute("data-icon-off");
    
        if (detectButton.classList.contains("active")) {
            detectButton.innerHTML = `<img src="${eyeIconOn}" class="icon eye_icon_on"> Deepfake Detection: On`;
        } else {
            detectButton.innerHTML = `<img src="${eyeIconOff}" class="icon eye_icon_off"> Deepfake Detection: Off`;
        }
    }
    

    // -------------------------------------------------------------------------
    // CAMERA BUTTON: toggles camera on/off 
    // (If you want detection auto-start, add isDetecting=true here)
    // -------------------------------------------------------------------------
    cameraButton.addEventListener("click", async function () {
        if (!isCameraOn) {
            await startCamera();
        } else {
            stopCamera();
    
            // Stop detection if you want
            isDetecting = false;
            detectButton.classList.remove("active");
    
            // Force the detect button to show "Off" text/icons
            const eyeIconOff = detectButton.getAttribute("data-icon-off");
            detectButton.innerHTML = `<img src="${eyeIconOff}" class="icon eye_icon_off"> Deepfake Detection: Off`;
        }
    });


    
    async function detectDeepfakeLoop(signal) {
        console.log("detectDeepfakeLoop entered; isDetecting =", isDetecting);

        // If camera is on, do a continuous loop:
        if (isCameraOn) {
            while (isDetecting) {
                const imageData = captureWebcamFrame(cameraFeed);
                selectedDetectVideo = null
                if (!imageData) {
                    // If not ready, wait a bit and retry
                    await new Promise(resolve => setTimeout(resolve, 300));
                    continue;
                }

                // statusInfo.innerHTML = "Detecting (webcam)...";
                try {
                    const response = await fetch("/predict_deepfake", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      credentials: "same-origin",        // <— send login cookie
                      cache: "no-cache",
                      body: JSON.stringify({ image: imageData, source: "webcam" }),
                    });

                    // Gracefully handle auth/quota first
                    if (response.redirected || response.status === 401) {
                      statusInfo.innerHTML = "Login required. Stopping stream.";
                      break;
                    }
                    if (response.status === 429) {
                      let j = {};
                      try { j = await response.json(); } catch {}
                      statusInfo.innerHTML = `Free quota reached. Try again in ~${j.retry_in_minutes ?? 'a few'} min.`;
                      break;
                    }

                    // Try JSON; if it isn't, show short text for debugging
                    let data;
                    try {
                      data = await response.json();
                    } catch (e) {
                      const text = await response.text();
                      console.warn("Non-JSON from server:", response.status, text.slice(0,200));
                      statusInfo.innerHTML = `Server error ${response.status}.`;
                      await new Promise(r => setTimeout(r, 600));
                      continue;
                    }



                    if (data.annotated_frame) {
                        console.log(data.annotated_frame)
                        // If you want to overlay annotated frame
                        deepfakeImage.src = data.annotated_frame;
                        deepfakeImage.style.display = "block";
                    } else {
                        // No annotated frame => hide overlay
                        deepfakeImage.style.display = "none";
                      }

                    if (data.results) {
                        console.log("Real-time deepfake detection successful.");
                        statusInfo.innerHTML = `Detecting in real-time`;
                        // Show your info in parametersInfo
                        if (data.results.face_id !== undefined) {
                            parametersInfo.innerHTML = `
                            <div style="text-align: left;">
                                <b>FPS:</b> ${data.fps}<br>
                                <b>Label:</b> ${data.results.label}<br>
                                <b>Confidence:</b> ${(data.results.confidence * 100).toFixed(2)}%<br>
                                <b>Is Fake:</b> ${data.results.is_fake ? "Yes" : "No"}<br>
                                <b>Probabilities:</b> ${data.results.probabilities.join(", ")}
                            </div>
                            `;
                        }
                    } else {
                        console.log("No deepfake detected.");
                        statusInfo.innerHTML = "No deepfake detected.";
                        deepfakeImage.style.display = "none";
                    }

                } catch (error) {
                    console.error("Error detecting deepfake:", error);
                    statusInfo.innerHTML = "Error detecting deepfake.";
                    deepfakeImage.style.display = "none";
                }

                // short delay so we don't spam the server too fast
                await new Promise(resolve => setTimeout(resolve, 300));
            }

            console.log("Exiting camera real-time loop; isDetecting =", isDetecting);
            // If you had an overlay image, you can hide it here
            deepfakeImage.style.display = "none";
        }
        // Else if user selected a video, run the single-pass code:
        else if (selectedDetectVideo && isDetecting) {
            console.log("Processing selected video:", selectedDetectVideo.name);
            statusInfo.innerHTML = "Processing selected video.";

            const reader = new FileReader();
            reader.readAsDataURL(selectedDetectVideo);
            reader.onload = async function (event) {
                let imageData = event.target.result;
                let sourceType= "video";

                console.log("Sending video to server for deepfake detection...");
                statusInfo.innerHTML = "Detecting...";

                try {
                    const response = await fetch("/predict_deepfake", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ image: imageData, source: sourceType }),
                    });

                    const data = await response.json();

                    if (data.results) {
                        console.log("Deepfake detection successful.");
                        statusInfo.innerHTML = `Detection Process Completed`;
                        if (data.results.video_path) {
                            parametersInfo.innerHTML = `
                                <div style="text-align: left;">
                                    <b>Total Frames:</b> ${data.results.total_frames} <br>
                                    <b>Frames with Faces:</b> ${data.results.frames_with_faces} <br>
                                    <b>No Face Frames:</b> ${data.results.no_face_frames} <br>
                                    <b>Real Frames:</b> ${data.results.real_frames} <br>
                                    <b>Fake Frames:</b> ${data.results.fake_frames} <br>
                                    <b>Fake Percentage:</b> ${data.results.fake_percentage.toFixed(2)}% <br>
                                    <b>Avg Processing Time:</b> ${data.results.avg_processing_time.toFixed(4)}s <br>
                                    <b>Verdict:</b> ${data.results.verdict} <br>
                                    <b>Confidence:</b> ${(data.results.confidence * 100).toFixed(2)}% <br>
                                </div>
                            `;
                        }
                        // For example, if you want to show the processed video:
                        // showVideoOnCameraFeed(data.results.output_path);
                        const lineBreak = document.createElement("br");
                        statusInfo.appendChild(lineBreak);
                        const showVideoButton = document.createElement("button");
                        showVideoButton.textContent = "\n---Play video---";
                        showVideoButton.addEventListener("click", () => showVideoOnCameraFeed(data.results.output_path));
                        statusInfo.appendChild(showVideoButton);
                    } else {
                        console.log("No deepfake detected or error in video processing.");
                        statusInfo.innerHTML = "No deepfake detected.";
                    }
                } catch (error) {
                    console.error("Error processing video:", error);
                    statusInfo.innerHTML = "Error processing video.";
                }

                isDetecting = false;
                detectButton.classList.remove("active");
                updateDetectButtonUI();
                console.log("Deepfake detection stopped.");
            };
        }
    }

    window.toggleCollapse = function (id) {
        var content = document.getElementById(id);
        if (id === "detectVideoContainer") {
            if (detectVideoGrid.children.length > 0 && content.classList.contains("open")) {
                return;
            }
        }
        content.classList.toggle("open");
    };
});
