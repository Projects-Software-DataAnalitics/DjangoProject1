const menuBtn = document.getElementById("menu-btn");
menuBtn.addEventListener("click", toggleSidebar);

function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    const content = document.getElementById("content");
    if (sidebar.style.width === "200px") {
        sidebar.style.width = "0";
        content.style.marginLeft = "0";
    } else {
        sidebar.style.width = "200px";
        content.style.marginLeft = "200px";
    }
}

const instructorData = JSON.parse(sessionStorage.getItem('loggedInstructor'));
if (!instructorData) {
    window.location.href = "/";
}

function getCsrfToken() {
    const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
    return cookieMatch ? cookieMatch[1] : null;
}

document.getElementById("personal-info-btn").addEventListener("click", showPersonalInfo);
document.getElementById("my-courses-btn").addEventListener("click", showMyCourses);
document.getElementById("grades-btn").addEventListener("click", showGrades);
document.getElementById("announcements-btn").addEventListener("click", showAnnouncements);
document.getElementById("logout-btn").addEventListener("click", logout);

function showPersonalInfo() {
    const infoDiv = document.getElementById("personal-info");
    infoDiv.innerHTML = `
        <h2>Personal Information</h2>
        <p><strong>Name:</strong> ${instructorData.firstName} ${instructorData.lastName}</p>
        <p><strong>Username:</strong> ${instructorData.username}</p>
        <p><strong>Course:</strong> ${instructorData.courses.join(", ")}</p>
    `;
}

function showMyCourses() {
    const infoDiv = document.getElementById("personal-info");
    infoDiv.innerHTML = `
        <h2>My Courses</h2>
        <ul>
            ${instructorData.courses.map(course => `<li>${course}</li>`).join('')}
        </ul>
    `;
}

function showGrades() {
    const infoDiv = document.getElementById("personal-info");
    const coursesOptions = instructorData.courses.map(course => 
        `<option value="${course}">${course}</option>`
    ).join('');
    
    infoDiv.innerHTML = `
        <h2>Grades</h2>
        <div style="margin-top: 24px;">
            <label for="course-select" style="display: block; margin-bottom: 8px; font-weight: 600; color: #0f172a;">Select Course</label>
            <select id="course-select" style="padding: 8px; border: 1px solid #cbd5e1; border-radius: 8px; width: 100%; max-width: 400px; background: #f8fafc; font-size: 14px; cursor: pointer;">
                <option value="">-- Select a course --</option>
                ${coursesOptions}
            </select>
        </div>
        <div id="file-upload-section" style="margin-top: 24px; display: none;"></div>
        <div id="upload-status" class="upload-status" style="margin-top: 16px;"></div>
    `;
    
    const courseSelect = document.getElementById("course-select");
    courseSelect.addEventListener("change", function() {
        const selectedCourse = this.value;
        const fileUploadSection = document.getElementById("file-upload-section");
        
        if (selectedCourse) {
            fileUploadSection.style.display = "block";
            updateFileUploadSection(selectedCourse);
            refreshUploadStatus(selectedCourse);
        } else {
            fileUploadSection.style.display = "none";
            refreshUploadStatus(null);
        }
    });

    refreshUploadStatus(null);
}

function getUploadStorageKey(course) {
    return `uploadedGrades_${instructorData.username}_${course}`;
}

function refreshUploadStatus(course) {
    const statusEl = document.getElementById("upload-status");
    if (!statusEl) return;

    if (!course) {
        statusEl.textContent = "";
        statusEl.style.color = "#475569";
        return;
    }

    const stored = localStorage.getItem(getUploadStorageKey(course));
    if (stored) {
        const info = JSON.parse(stored);
        const uploadedAt = new Date(info.timestamp).toLocaleString();
        statusEl.textContent = `Latest upload (${info.filename}) on ${uploadedAt}`;
        statusEl.style.color = "#15803d";
    } else {
        statusEl.textContent = "No CSV uploaded for this course yet.";
        statusEl.style.color = "#475569";
    }
}

function updateFileUploadSection(course) {
    const fileUploadSection = document.getElementById("file-upload-section");
    fileUploadSection.innerHTML = `
        <label for="csv-file-input" style="display: block; margin-bottom: 8px; font-weight: 600; color: #0f172a;">Upload CSV File</label>
        <input type="file" id="csv-file-input" accept=".csv" style="padding: 8px; border: 1px solid #cbd5e1; border-radius: 8px; width: 100%; max-width: 400px; background: #f8fafc;">
        <p style="margin-top: 8px; color: #475569; font-size: 13px;">Expected columns: student_username, course_name, midterm, assignment, final</p>
    `;

    document.getElementById("csv-file-input").addEventListener("change", function(e) {
        const file = e.target.files[0];
        if (file) {
            uploadGradesFile(file, course);
        }
    });
}

function uploadGradesFile(file, course) {
    const statusEl = document.getElementById("upload-status");
    if (!course) {
        statusEl.textContent = "Please select a course.";
        statusEl.style.color = "#b91c1c";
        return;
    }

    const formData = new FormData();
    formData.append("csv_file", file);

    statusEl.textContent = "Uploading...";
    statusEl.style.color = "#0f172a";

    fetch("/grades/upload/", {
        method: "POST",
        headers: {
            "X-CSRFToken": getCsrfToken() || ""
        },
        body: formData,
        credentials: "same-origin"
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === "ok") {
            localStorage.setItem(
                getUploadStorageKey(course),
                JSON.stringify({ filename: file.name, timestamp: Date.now() })
            );
            statusEl.textContent = `Grades uploaded successfully for ${course}.`;
            statusEl.style.color = "#15803d";
            refreshUploadStatus(course);
        } else {
            statusEl.textContent = data.error || "Upload failed.";
            statusEl.style.color = "#b91c1c";
        }
    })
    .catch(() => {
        statusEl.textContent = "Upload error.";
        statusEl.style.color = "#b91c1c";
    });
}

function showAnnouncements() {
    const infoDiv = document.getElementById("personal-info");
    infoDiv.innerHTML = `<h2>Announcements Section (coming soon)</h2>`;
}

function logout() {
    sessionStorage.clear();
    window.location.href = "/";
}

document.getElementById("personal-info").innerHTML = "";


