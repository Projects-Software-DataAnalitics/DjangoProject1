// ----------------------------
// Toggle sidebar
// ----------------------------
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
// Get logged faculty head
// ----------------------------
const facultyHeadData = JSON.parse(sessionStorage.getItem('loggedFacultyHead'));
if (!facultyHeadData) {
    window.location.href = "/";
}

// ----------------------------
// Sidebar button listeners
// ----------------------------
document.getElementById("personal-info-btn").addEventListener("click", showPersonalInfo);
document.getElementById("my-courses-btn").addEventListener("click", showMyCourses);
document.getElementById("announcements-btn").addEventListener("click", showAnnouncements);
document.getElementById("logout-btn").addEventListener("click", logout);

// ----------------------------
// Functions
// ----------------------------
function showPersonalInfo() {
    const infoDiv = document.getElementById("personal-info");
    infoDiv.innerHTML = `
        <h2>Personal Information</h2>
        <p><strong>Name:</strong> ${facultyHeadData.firstName} ${facultyHeadData.lastName}</p>
        <p><strong>Username:</strong> ${facultyHeadData.username}</p>
        <p><strong>Department:</strong> ${facultyHeadData.department || 'N/A'}</p>
        <p><strong>Faculty:</strong> ${facultyHeadData.faculty || 'N/A'}</p>
        <p><strong>Courses:</strong> ${facultyHeadData.courses.join(", ")}</p>
    `;
}

function showMyCourses() {
    const infoDiv = document.getElementById("personal-info");
    infoDiv.innerHTML = `
        <h2>My Courses</h2>
        <ul>
            ${facultyHeadData.courses.map(course => `<li>${course}</li>`).join('')}
        </ul>
    `;
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


