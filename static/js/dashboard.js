// Function to toggle fullscreen mode
function toggleFullscreen(element) {
    const fullscreenOverlay = document.createElement("div");
    fullscreenOverlay.classList.add("fullscreen-overlay");

    const fullscreenImg = document.createElement("img");
    fullscreenImg.src = element.src; // Use the current source of the element

    const exitBtn = document.createElement("button");
    exitBtn.classList.add("fullscreen-exit-btn");
    exitBtn.innerHTML = '<i class="fas fa-compress"></i>';
    exitBtn.addEventListener("click", () => {
        document.body.removeChild(fullscreenOverlay);
        document.exitFullscreen();
    });

    fullscreenOverlay.appendChild(fullscreenImg);
    fullscreenOverlay.appendChild(exitBtn);
    document.body.appendChild(fullscreenOverlay);

    // Request fullscreen for the overlay or the image itself
    if (fullscreenOverlay.requestFullscreen) {
        fullscreenOverlay.requestFullscreen();
    } else if (fullscreenOverlay.webkitRequestFullscreen) { /* Safari */
        fullscreenOverlay.webkitRequestFullscreen();
    } else if (fullscreenOverlay.msRequestFullscreen) { /* IE11 */
        fullscreenOverlay.msRequestFullscreen();
    }

    fullscreenOverlay.classList.add("active");
}

// Function to handle camera grid layout
function updateCameraGrid() {
    const grid = document.querySelector('.cameras-grid');
    const cameras = grid.querySelectorAll('.camera-feed');
    const count = cameras.length;

    if (count === 0) return;

    // Remove any existing grid classes
    grid.className = 'cameras-grid';

    // Add appropriate grid class based on camera count
    if (count === 1) {
        grid.classList.add('single-camera');
    } else if (count === 2) {
        grid.classList.add('two-cameras');
    } else if (count === 3 || count === 4) {
        grid.classList.add('four-cameras');
    } else {
        grid.classList.add('multi-cameras');
    }
}

// Function to handle camera connection status updates
function updateCameraStatus(cameraId, isActive) {
    const camera = document.querySelector(`#camera-${cameraId}`);
    if (camera) {
        const statusElement = camera.querySelector('.camera-status');
        statusElement.className = `camera-status ${isActive ? 'active' : 'inactive'}`;
        statusElement.textContent = isActive ? 'متصل' : 'غير متصل';
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    // Initial setup functions
    updateAlertsList();
    setupLogout();
    setupCameraControls();
    fetchConnectedCamerasCount();

    // Event listeners - Check if element exists before adding listener
    const refreshBtn = document.getElementById("refreshCamerasBtn");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", fetchConnectedCamerasCount);
    }

    // Periodically fetch latest alerts and camera count
    setInterval(updateAlertsList, 10000); // Every 10 seconds
    setInterval(fetchConnectedCamerasCount, 30000); // Every 30 seconds

    updateCameraGrid();

    // Handle fullscreen change events
    document.addEventListener('fullscreenchange', function () {
        const fullscreenElement = document.fullscreenElement;
        if (!fullscreenElement) {
            // Reset all fullscreen buttons when exiting fullscreen
            document.querySelectorAll('.fullscreen-btn i').forEach(icon => {
                icon.classList.remove('fa-compress');
                icon.classList.add('fa-expand');
            });
        }
    });

    // Handle camera feed errors
    document.querySelectorAll('.camera-feed img').forEach(img => {
        img.addEventListener('error', function () {
            const cameraId = this.parentElement.id.replace('camera-', '');
            updateCameraStatus(cameraId, false);
        });

        img.addEventListener('load', function () {
            const cameraId = this.parentElement.id.replace('camera-', '');
            updateCameraStatus(cameraId, true);
        });
    });

    // إضافة زر الخروج من وضع ملء الشاشة لكل كاميرا
    document.querySelectorAll('.camera-feed').forEach(feed => {
        const exitBtn = document.createElement('button');
        exitBtn.className = 'exit-fullscreen-btn';
        exitBtn.innerHTML = '<i class="fas fa-compress"></i>';
        feed.appendChild(exitBtn);
    });

    // معالجة نقر زر التكبير
    document.querySelectorAll('.fullscreen-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const feedId = this.getAttribute('data-feed-id');
            const feed = document.getElementById(feedId);
            const img = feed.querySelector('img');

            if (!document.fullscreenElement) {
                if (img.requestFullscreen) {
                    img.requestFullscreen();
                } else if (img.webkitRequestFullscreen) { /* Safari */
                    img.webkitRequestFullscreen();
                } else if (img.msRequestFullscreen) { /* IE11 */
                    img.msRequestFullscreen();
                }
                this.querySelector('i').classList.replace('fa-expand', 'fa-compress');
            } else {
                if (document.exitFullscreen) {
                    document.exitFullscreen();
                } else if (document.webkitExitFullscreen) { /* Safari */
                    document.webkitExitFullscreen();
                } else if (document.msExitFullscreen) { /* IE11 */
                    document.msExitFullscreen();
                }
                this.querySelector('i').classList.replace('fa-compress', 'fa-expand');
            }
        });
    });

    // معالجة ضغط مفتاح ESC
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && document.fullscreenElement) {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            }
        }
    });

    // معالجة نقر زر الخروج من وضع ملء الشاشة
    document.querySelectorAll('.exit-fullscreen-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const feed = this.closest('.camera-feed');
            feed.classList.remove('fullscreen');

            // تحديث أيقونة زر التكبير المرتبط
            const feedId = feed.getAttribute('id');
            const fullscreenBtn = document.querySelector(`[data-feed-id="${feedId}"]`);
            const icon = fullscreenBtn.querySelector('i');
            icon.classList.remove('fa-compress');
            icon.classList.add('fa-expand');
        });
    });
});

// Fetches and updates the latest alerts list
function updateAlertsList() {
    fetch("/get_latest_alerts/")
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const alertsGrid = document.getElementById("alertsGrid");
            if (!alertsGrid) {
                console.log("Alerts grid element not found");
                return;
            }

            let alertsHTML = "";
            if (data.alerts && data.alerts.length > 0) {
                data.alerts.forEach(alert => {
                    alertsHTML += `
                        <div class="alert-card">
                            <h3>${alert.camera_name}</h3>
                            <p class="alert-description">${alert.description}</p>
                            <span class="alert-time">${alert.timestamp}</span>
                        </div>
                    `;
                });
            } else {
                alertsHTML = `
                    <div class="no-alerts">
                        لا توجد تنبيهات لعرضها
                    </div>
                `;
            }
            alertsGrid.innerHTML = alertsHTML;
        })
        .catch(error => {
            console.error("Error fetching alerts:", error);
            // Don't update the DOM if there's an error
        });
}

// Sets up the logout button functionality
function setupLogout() {
    const logoutForm = document.getElementById("logoutForm");
    if (logoutForm) {
        logoutForm.addEventListener("submit", function (e) {
            e.preventDefault();
            if (confirm("هل أنت متأكد أنك تريد تسجيل الخروج؟")) {
                this.submit();
            }
        });
    }
}

// Sets up camera control buttons (power and fullscreen)
function setupCameraControls() {
    const powerBtn = document.querySelector(".power-btn");
    if (powerBtn) {
        const cameraId = powerBtn.getAttribute("data-camera-id");
        powerBtn.addEventListener("click", () => toggleCamera(cameraId));
        // Set initial color based on assumed status (can be improved by backend passing status)
        const cameraStatusIndicator = document.getElementById("cameraStatusIndicator");
        if (cameraStatusIndicator && cameraStatusIndicator.classList.contains("off")) {
            powerBtn.querySelector('i').style.color = "var(--red-alert)";
        } else {
            powerBtn.querySelector('i').style.color = "var(--green-status)";
        }
    }

    const fullscreenBtn = document.querySelector(".fullscreen-btn");
    if (fullscreenBtn) {
        const targetFeedId = fullscreenBtn.getAttribute("data-target-feed");
        const targetFeed = document.getElementById(targetFeedId);
        if (targetFeed) {
            fullscreenBtn.addEventListener("click", () => toggleFullscreen(targetFeed));
        }
    }
}

// Toggles camera active/inactive status
function toggleCamera(cameraId) {
    const cameraStatusIndicator = document.getElementById("cameraStatusIndicator");
    let currentStatus = cameraStatusIndicator && !cameraStatusIndicator.classList.contains("off"); // Assume current status from indicator

    fetch(`/toggle_camera/${cameraId}/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken(),
        },
    })
        .then(response => response.json())
        .then(data => {
            const powerBtn = document.querySelector(".power-btn[data-camera-id='" + cameraId + "']");
            const mainCameraFeed = document.getElementById("mainCameraFeed");

            if (data.status) { // Camera is now active
                mainCameraFeed.src = `/video_feed/${cameraId}/?t=${new Date().getTime()}`; // Reload feed
                if (powerBtn) powerBtn.querySelector('i').style.color = "var(--green-status)";
                if (cameraStatusIndicator) {
                    cameraStatusIndicator.textContent = "Camera on";
                    cameraStatusIndicator.classList.remove("off");
                }
            } else { // Camera is now inactive
                mainCameraFeed.src = "{% static 'images/camera_off.jpg' %}"; // Placeholder for camera off
                if (powerBtn) powerBtn.querySelector('i').style.color = "var(--red-alert)";
                if (cameraStatusIndicator) {
                    cameraStatusIndicator.textContent = "Camera off";
                    cameraStatusIndicator.classList.add("off");
                }
            }
        })
        .catch(error => {
            console.error("Error toggling camera:", error);
            // Revert UI if error occurred
            const powerBtn = document.querySelector(".power-btn[data-camera-id='" + cameraId + "']");
            if (powerBtn) powerBtn.querySelector('i').style.color = currentStatus ? "var(--green-status)" : "var(--red-alert)";
            if (cameraStatusIndicator) {
                cameraStatusIndicator.textContent = currentStatus ? "Camera on" : "Camera off";
                cameraStatusIndicator.classList.toggle("off", !currentStatus);
            }
        });
}

// Fetches and displays the count of connected cameras
function fetchConnectedCamerasCount() {
    fetch("/get_cameras/") // Assuming this endpoint returns a list of cameras
        .then(response => response.json())
        .then(data => {
            const connectedCameraCountElement = document.getElementById("connectedCameraCount");
            if (connectedCameraCountElement) {
                // Filter active cameras if the endpoint returns all cameras
                const activeCameras = data.cameras.filter(camera => camera.is_active);
                connectedCameraCountElement.textContent = activeCameras.length;
            }
        })
        .catch(error => console.error("Error fetching connected cameras count:", error));
}

// Gets CSRF token from cookies
function getCsrfToken() {
    const name = "csrftoken";
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + "=")) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
