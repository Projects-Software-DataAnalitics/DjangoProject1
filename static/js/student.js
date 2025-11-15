// ----------------------------
// Function to open/close the sidebar
// ----------------------------
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

// Attach toggle function to menu button
document.getElementById("menu-btn").addEventListener("click", toggleSidebar);

// ----------------------------
// Get logged student
// ----------------------------
const studentData = JSON.parse(sessionStorage.getItem('loggedStudent'));
if (!studentData) {
    window.location.href = "/";
}

// ----------------------------
// Add event listener for sidebar buttons
// ----------------------------
document.getElementById("personal-info-btn").addEventListener("click", showPersonalInfo);
document.getElementById("my-courses-btn").addEventListener("click", showMyCourses);
document.getElementById("grades-btn").addEventListener("click", showGrades);
document.getElementById("announcements-btn").addEventListener("click", showAnnouncements);
document.getElementById("logout-btn").addEventListener("click", logout);

// ----------------------------
// Functions for sidebar actions
// ----------------------------
function showPersonalInfo() {
    const infoDiv = document.getElementById("personal-info");
    infoDiv.innerHTML = `
        <h2>Personal Information</h2>
        <p><strong>Name:</strong> ${studentData.firstName} ${studentData.lastName}</p>
        <p><strong>Username:</strong> ${studentData.username}</p>
        <p><strong>Department:</strong> ${studentData.department}</p>
        <p><strong>Class:</strong> ${studentData.class}</p>
        <p><strong>Courses:</strong> ${studentData.courses.join(", ")}</p>
    `;
}

function showMyCourses() {
    const infoDiv = document.getElementById("personal-info");
    infoDiv.innerHTML = `
        <h2>My Courses</h2>
        <ul>
            ${studentData.courses.map(course => `<li>${course}</li>`).join('')}
        </ul>
    `;
}

function showGrades() {
    document.getElementById("personal-info").innerHTML = "<h2>Grades Section (coming soon)</h2>";
}

function showAnnouncements() {
    document.getElementById("personal-info").innerHTML = "<h2>Announcements Section (coming soon)</h2>";
}

function logout() {
    sessionStorage.clear();
    window.location.href = "/";
}

// Default view: keep content empty
document.getElementById("personal-info").innerHTML = "";

