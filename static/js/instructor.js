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


