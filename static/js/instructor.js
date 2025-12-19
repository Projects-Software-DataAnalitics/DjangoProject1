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

let instructorData = JSON.parse(sessionStorage.getItem('loggedInstructor'));
if (!instructorData) {
    window.location.href = "/";
} else {
    const jsonPathElement = document.getElementById('instructor-json-path');
    const jsonPath = jsonPathElement ? jsonPathElement.dataset.path : '/static/json/instructors.json';
    
    fetch(jsonPath + '?t=' + Date.now())
        .then(response => response.json())
        .then(data => {
            const currentInstructor = data.find(i => i.username === instructorData.username);
            if (currentInstructor) {
                sessionStorage.setItem('loggedInstructor', JSON.stringify(currentInstructor));
                window.instructorData = currentInstructor;
                instructorData = currentInstructor;
            }
        })
        .catch(() => {
        });
    
    function getCsrfToken() {
        const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
        return cookieMatch ? cookieMatch[1] : null;
    }
    fetch('/instructor/set-session/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCsrfToken() || ''
        },
        body: `username=${encodeURIComponent(instructorData.username)}`
    }).catch(() => {});
}


function getCsrfToken() {
    const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
    return cookieMatch ? cookieMatch[1] : null;
}

document.getElementById("logout-btn").addEventListener("click", logout);

const pageType = document.body.dataset.page || '';
if (pageType === 'profile') {
    showPersonalInfo();
} else if (pageType === 'my_courses') {
    showMyCourses();
} else if (pageType === 'grades') {
    showGrades();
} else if (pageType === 'announcements') {
    showAnnouncements();
}

function showPersonalInfo() {
    const infoDiv = document.getElementById("personal-info");
    const jsonPathElement = document.getElementById('instructor-json-path');
    const jsonPath = jsonPathElement ? jsonPathElement.dataset.path : '/static/json/instructors.json';
    
    const storedData = sessionStorage.getItem('loggedInstructor');
    if (!storedData) {
        window.location.href = "/";
        return;
    }
    
    const storedInstructor = JSON.parse(storedData);
    const currentUsername = storedInstructor.username;
    
    fetch(jsonPath + '?t=' + Date.now())
        .then(response => response.json())
        .then(data => {
            const currentInstructor = data.find(i => i.username === currentUsername);
            if (currentInstructor) {
                sessionStorage.setItem('loggedInstructor', JSON.stringify(currentInstructor));
                infoDiv.innerHTML = `
                    <h2>Personal Information</h2>
                    <p><strong>Name:</strong> ${currentInstructor.firstName} ${currentInstructor.lastName}</p>
                    <p><strong>Username:</strong> ${currentInstructor.username}</p>
                    <p><strong>Faculty:</strong> ${currentInstructor.faculty || 'N/A'}</p>
                    <p><strong>Department:</strong> ${currentInstructor.department || 'N/A'}</p>
                    <p><strong>Course:</strong> ${(currentInstructor.courses || []).join(", ")}</p>
                `;
            } else {
                const freshData = JSON.parse(sessionStorage.getItem('loggedInstructor'));
                if (freshData) {
                    infoDiv.innerHTML = `
                        <h2>Personal Information</h2>
                        <p><strong>Name:</strong> ${freshData.firstName} ${freshData.lastName}</p>
                        <p><strong>Username:</strong> ${freshData.username}</p>
                        <p><strong>Faculty:</strong> ${freshData.faculty || 'N/A'}</p>
                        <p><strong>Department:</strong> ${freshData.department || 'N/A'}</p>
                        <p><strong>Course:</strong> ${(freshData.courses || []).join(", ")}</p>
                    `;
                }
            }
        })
        .catch(() => {
            const freshData = JSON.parse(sessionStorage.getItem('loggedInstructor'));
            if (freshData) {
                infoDiv.innerHTML = `
                    <h2>Personal Information</h2>
                    <p><strong>Name:</strong> ${freshData.firstName} ${freshData.lastName}</p>
                    <p><strong>Username:</strong> ${freshData.username}</p>
                    <p><strong>Faculty:</strong> ${freshData.faculty || 'N/A'}</p>
                    <p><strong>Department:</strong> ${freshData.department || 'N/A'}</p>
                    <p><strong>Course:</strong> ${(freshData.courses || []).join(", ")}</p>
                `;
            }
        });
}

function showMyCourses() {
    const infoDiv = document.getElementById("personal-info");
    const jsonPathElement = document.getElementById('instructor-json-path');
    const jsonPath = jsonPathElement ? jsonPathElement.dataset.path : '/static/json/instructors.json';
    
    const storedData = sessionStorage.getItem('loggedInstructor');
    if (!storedData) {
        window.location.href = "/";
        return;
    }
    
    const storedInstructor = JSON.parse(storedData);
    const currentUsername = storedInstructor.username;
    
    fetch(jsonPath + '?t=' + Date.now())
        .then(response => response.json())
        .then(data => {
            const currentInstructor = data.find(i => i.username === currentUsername);
            if (currentInstructor) {
                sessionStorage.setItem('loggedInstructor', JSON.stringify(currentInstructor));
                infoDiv.innerHTML = `
                    <h2>My Courses</h2>
                    <ul>
                        ${(currentInstructor.courses || []).map(course => `<li>${course}</li>`).join('')}
                    </ul>
                `;
            } else {
                infoDiv.innerHTML = `
                    <h2>My Courses</h2>
                    <ul>
                        <li>No courses found.</li>
                    </ul>
                `;
            }
        })
        .catch(() => {
            const freshData = JSON.parse(sessionStorage.getItem('loggedInstructor'));
            if (freshData) {
                infoDiv.innerHTML = `
                    <h2>My Courses</h2>
                    <ul>
                        ${(freshData.courses || []).map(course => `<li>${course}</li>`).join('')}
                    </ul>
                `;
            } else {
                infoDiv.innerHTML = `
                    <h2>My Courses</h2>
                    <ul>
                        <li>No courses found.</li>
                    </ul>
                `;
            }
        });
}

function showGrades() {
    const infoDiv = document.getElementById("personal-info");
    const jsonPathElement = document.getElementById('instructor-json-path');
    const jsonPath = jsonPathElement ? jsonPathElement.dataset.path : '/static/json/instructors.json';
    
    const storedData = sessionStorage.getItem('loggedInstructor');
    if (!storedData) {
        window.location.href = "/";
        return;
    }
    
    const storedInstructor = JSON.parse(storedData);
    const currentUsername = storedInstructor.username;
    
    fetch(jsonPath + '?t=' + Date.now())
        .then(response => response.json())
        .then(data => {
            const currentInstructor = data.find(i => i.username === currentUsername);
            let courses = [];
            if (currentInstructor) {
                sessionStorage.setItem('loggedInstructor', JSON.stringify(currentInstructor));
                courses = currentInstructor.courses || [];
            } else {
                const freshData = JSON.parse(sessionStorage.getItem('loggedInstructor'));
                courses = freshData ? (freshData.courses || []) : [];
            }
            
            const coursesOptions = courses.map(course => 
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
        })
        .catch(() => {
            const freshData = JSON.parse(sessionStorage.getItem('loggedInstructor'));
            const courses = freshData ? (freshData.courses || []) : [];
            const coursesOptions = courses.map(course => 
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
        });
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


