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

document.addEventListener("DOMContentLoaded", function() {
    const menuBtn = document.getElementById("menu-btn");
    if (menuBtn) {
        menuBtn.addEventListener("click", toggleSidebar);
    }
});

let instructorData = null;
try {
    const stored = sessionStorage.getItem('loggedInstructor');
    if (stored) {
        instructorData = JSON.parse(stored);
    }
} catch (e) {
    instructorData = null;
}

if (!instructorData) {
    window.location.href = "/";
} else {
    const jsonPathElement = document.getElementById('instructor-json-path');
    const jsonPath = jsonPathElement ? jsonPathElement.dataset.path : '/static/json/instructors.json';
    
    const fetchWithTimeout = (url, options, timeout = 5000) => {
        return Promise.race([
            fetch(url, options),
            new Promise((_, reject) => 
                setTimeout(() => reject(new Error('Request timeout')), timeout)
            )
        ]);
    };
    
    fetchWithTimeout(jsonPath + '?t=' + Date.now(), {}, 3000)
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            const currentInstructor = data.find(i => i.username === instructorData.username);
            if (currentInstructor) {
                sessionStorage.setItem('loggedInstructor', JSON.stringify(currentInstructor));
                window.instructorData = currentInstructor;
                instructorData = currentInstructor;
            }
        })
        .catch(() => {});
    
    function getCsrfToken() {
        const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
        return cookieMatch ? cookieMatch[1] : null;
    }
    
    fetchWithTimeout('/instructor/set-session/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCsrfToken() || ''
        },
        body: `username=${encodeURIComponent(instructorData.username)}`
    }, 3000).catch(() => {});
}


function getCsrfToken() {
    const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
    return cookieMatch ? cookieMatch[1] : null;
}

document.addEventListener("DOMContentLoaded", function() {
    const logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", logout);
    }
    
    const pageType = document.body.dataset.page || '';
    // Check if we're on the instructor_grades_page template (which has its own content)
    // The new template uses Django rendering, so showGrades() should NEVER run
    const personalInfo = document.querySelector('#personal-info');
    const coursesTable = personalInfo ? personalInfo.querySelector('#courses-table') : null;
    const headerCells = coursesTable ? coursesTable.querySelectorAll('thead th') : [];
    
    const isGradesPageTemplate = window.instructorGradesPageLoaded || 
                                 window.instructorGradesPageTemplate ||
                                 document.querySelector('#grades-title') !== null ||
                                 (headerCells.length > 1); // New template has 3 columns
    
    if (pageType === 'profile') {
        showPersonalInfo();
    } else if (pageType === 'my_courses') {
        showMyCourses();
    } else if (pageType === 'grades') {
        // NEVER call showGrades() - the new template (instructor_grades_page.html) handles everything
        // showGrades() is only for the old system which is no longer used
        if (!isGradesPageTemplate) {
            console.warn('showGrades() not called - new template system in use');
        }
    } else if (pageType === 'announcements') {
        showAnnouncements();
    }
});

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
    // DEPRECATED: This function is no longer used
    // The new template system (instructor_grades_page.html) handles course selection via Django
    // Always return early to prevent any override
    console.log('showGrades() blocked - new template system in use');
    return;
    
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
            
            let coursesTableRows = '';
            if (courses.length > 0) {
                coursesTableRows = courses.map((course, index) => {
                    let rowStyle = 'cursor: pointer; border-bottom: 1px solid #ddd;';
                    if (index % 2 === 0) {
                        rowStyle += ' background-color: #f8fafc;';
                    }
                    return `<tr class="course-row" data-course="${course}" style="${rowStyle}">
                        <td style="padding: 12px; border: 1px solid #ddd;">${course}</td>
                    </tr>`;
                }).join('');
            } else {
                coursesTableRows = '<tr><td style="padding: 12px; text-align: center; color: #666; border: 1px solid #ddd;">No courses available</td></tr>';
            }
            
            infoDiv.innerHTML = `
                <h2>Grades</h2>
                <div style="margin-top: 24px; display: flex; justify-content: center;">
                    <table id="courses-table" style="width: 100%; max-width: 500px; border-collapse: collapse; margin-top: 20px;">
                        <thead>
                            <tr style="background-color: #0b5fff; color: white;">
                                <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Course Name</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${coursesTableRows}
                        </tbody>
                    </table>
                </div>
                <div id="file-upload-section" style="margin-top: 24px; display: none;"></div>
                <div id="upload-status" class="upload-status" style="margin-top: 16px;"></div>
            `;
            
            // Add click event listeners to course rows
            const courseRows = document.querySelectorAll('.course-row');
            courseRows.forEach((row, index) => {
                const originalBg = index % 2 === 0 ? '#f8fafc' : 'white';
                row.addEventListener('mouseenter', function() {
                    this.style.backgroundColor = '#e0f2fe';
                });
                row.addEventListener('mouseleave', function() {
                    this.style.backgroundColor = originalBg;
                });
                row.addEventListener('click', function() {
                    const courseName = this.dataset.course;
                    if (courseName) {
                        window.location.href = `/instructor/grades/${encodeURIComponent(courseName)}/`;
                    }
                });
            });
        })
        .catch(() => {
            const freshData = JSON.parse(sessionStorage.getItem('loggedInstructor'));
            const courses = freshData ? (freshData.courses || []) : [];
            
            let coursesTableRows = '';
            if (courses.length > 0) {
                coursesTableRows = courses.map((course, index) => {
                    let rowStyle = 'cursor: pointer; border-bottom: 1px solid #ddd;';
                    if (index % 2 === 0) {
                        rowStyle += ' background-color: #f8fafc;';
                    }
                    return `<tr class="course-row" data-course="${course}" style="${rowStyle}">
                        <td style="padding: 12px; border: 1px solid #ddd;">${course}</td>
                    </tr>`;
                }).join('');
            } else {
                coursesTableRows = '<tr><td style="padding: 12px; text-align: center; color: #666; border: 1px solid #ddd;">No courses available</td></tr>';
            }
            
            infoDiv.innerHTML = `
                <h2>Grades</h2>
                <div style="margin-top: 24px; display: flex; justify-content: center;">
                    <table id="courses-table" style="width: 100%; max-width: 500px; border-collapse: collapse; margin-top: 20px;">
                        <thead>
                            <tr style="background-color: #0b5fff; color: white;">
                                <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Course Name</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${coursesTableRows}
                        </tbody>
                    </table>
                </div>
                <div id="file-upload-section" style="margin-top: 24px; display: none;"></div>
                <div id="upload-status" class="upload-status" style="margin-top: 16px;"></div>
            `;
            
            // Add click event listeners to course rows
            const courseRows = document.querySelectorAll('.course-row');
            courseRows.forEach((row, index) => {
                const originalBg = index % 2 === 0 ? '#f8fafc' : 'white';
                row.addEventListener('mouseenter', function() {
                    this.style.backgroundColor = '#e0f2fe';
                });
                row.addEventListener('mouseleave', function() {
                    this.style.backgroundColor = originalBg;
                });
                row.addEventListener('click', function() {
                    const courseName = this.dataset.course;
                    if (courseName) {
                        window.location.href = `/instructor/grades/${encodeURIComponent(courseName)}/`;
                    }
                });
            });
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

document.addEventListener("DOMContentLoaded", function() {
    // Don't clear personal-info if it's the new grades page template
    const personalInfo = document.getElementById("personal-info");
    if (personalInfo && !window.instructorGradesPageLoaded && !window.instructorGradesPageTemplate) {
        // Only clear if it's not the new template
        const coursesTable = personalInfo.querySelector('#courses-table');
        if (!coursesTable || coursesTable.querySelectorAll('thead th').length <= 1) {
            personalInfo.innerHTML = "";
        }
    }
});


