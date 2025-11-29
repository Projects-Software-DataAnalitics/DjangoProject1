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

// ----------------------------
// Get logged instructor
// ----------------------------
const instructorData = JSON.parse(sessionStorage.getItem('loggedInstructor'));
if (!instructorData) {
    window.location.href = "/";
}

// ----------------------------
// Sidebar button listeners
// ----------------------------
document.getElementById("personal-info-btn").addEventListener("click", showPersonalInfo);
document.getElementById("my-courses-btn").addEventListener("click", showMyCourses);
document.getElementById("grades-btn").addEventListener("click", showGrades);
document.getElementById("announcements-btn").addEventListener("click", showAnnouncements);
document.getElementById("logout-btn").addEventListener("click", logout);

// ----------------------------
// Functions
// ----------------------------
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
        <div id="file-upload-section" style="margin-top: 24px; display: none;">
        </div>
    `;
    
    // Course selection event listener
    const courseSelect = document.getElementById("course-select");
    courseSelect.addEventListener("change", function() {
        const selectedCourse = this.value;
        const fileUploadSection = document.getElementById("file-upload-section");
        
        if (selectedCourse) {
            fileUploadSection.style.display = "block";
            updateFileUploadSection(selectedCourse);
        } else {
            fileUploadSection.style.display = "none";
        }
    });
}

function updateFileUploadSection(course) {
    const fileUploadSection = document.getElementById("file-upload-section");
    const storageKey = `uploadedFile_${instructorData.username}_${course}`;
    const uploadedFile = localStorage.getItem(storageKey);
    
    if (uploadedFile) {
        // File already uploaded - show file name with change/delete buttons
        const fileName = JSON.parse(uploadedFile).name;
        fileUploadSection.innerHTML = `
            <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #0f172a;">Upload CSV File</label>
            <div style="display: flex; align-items: center; gap: 12px; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; background: #f8fafc; max-width: 400px;">
                <span style="flex: 1; color: #0f172a;">${fileName}</span>
                <button id="change-file-btn" style="padding: 6px 12px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #0f172a; cursor: pointer; font-size: 12px;">Change</button>
                <button id="delete-file-btn" style="padding: 6px 12px; border: 1px solid #e11d48; border-radius: 6px; background: #fff; color: #e11d48; cursor: pointer; font-size: 12px;">Delete</button>
            </div>
            <input type="file" id="csv-file-input-hidden" accept=".csv" style="display: none;">
        `;
        
        // Change button event
        document.getElementById("change-file-btn").addEventListener("click", function() {
            document.getElementById("csv-file-input-hidden").click();
        });
        
        // Delete button event
        document.getElementById("delete-file-btn").addEventListener("click", function() {
            localStorage.removeItem(storageKey);
            updateFileUploadSection(course);
        });
        
        // Hidden file input change event
        document.getElementById("csv-file-input-hidden").addEventListener("change", function(e) {
            const file = e.target.files[0];
            if (file) {
                const fileData = {
                    name: file.name,
                    size: file.size,
                    type: file.type
                };
                localStorage.setItem(storageKey, JSON.stringify(fileData));
                updateFileUploadSection(course);
            }
        });
    } else {
        // No file uploaded - show upload input
        fileUploadSection.innerHTML = `
            <label for="csv-file-input" style="display: block; margin-bottom: 8px; font-weight: 600; color: #0f172a;">Upload CSV File</label>
            <input type="file" id="csv-file-input" accept=".csv" style="padding: 8px; border: 1px solid #cbd5e1; border-radius: 8px; width: 100%; max-width: 400px; background: #f8fafc;">
        `;
        
        // File input change event
        document.getElementById("csv-file-input").addEventListener("change", function(e) {
            const file = e.target.files[0];
            if (file) {
                const fileData = {
                    name: file.name,
                    size: file.size,
                    type: file.type
                };
                localStorage.setItem(storageKey, JSON.stringify(fileData));
                updateFileUploadSection(course);
            }
        });
    }
}

function showAnnouncements() {
    const infoDiv = document.getElementById("personal-info");
    infoDiv.innerHTML = `<h2>Announcements Section (coming soon)</h2>`;
}

function logout() {
    sessionStorage.clear();
    window.location.href = "/";
}

// Default view: keep content empty
document.getElementById("personal-info").innerHTML = "";


