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


document.getElementById("menu-btn").addEventListener("click", toggleSidebar);


const studentData = JSON.parse(sessionStorage.getItem('loggedStudent'));
if (!studentData) {
    window.location.href = "/";
}


document.getElementById("personal-info-btn").addEventListener("click", showPersonalInfo);
document.getElementById("my-courses-btn").addEventListener("click", showMyCourses);
document.getElementById("grades-btn").addEventListener("click", showGrades);
document.getElementById("announcements-btn").addEventListener("click", showAnnouncements);
document.getElementById("logout-btn").addEventListener("click", logout);


function showPersonalInfo() {
    const infoDiv = document.getElementById("personal-info");
    const gradesSection = document.getElementById("grades-section");
    infoDiv.innerHTML = `
        <h2>Personal Information</h2>
        <p><strong>Name:</strong> ${studentData.firstName} ${studentData.lastName}</p>
        <p><strong>Username:</strong> ${studentData.username}</p>
        <p><strong>Department:</strong> ${studentData.department}</p>
        <p><strong>Class:</strong> ${studentData.class}</p>
        <p><strong>Courses:</strong> ${studentData.courses.join(", ")}</p>
    `;
    if (gradesSection) {
        gradesSection.style.display = "none";
    }
}

function showMyCourses() {
    const infoDiv = document.getElementById("personal-info");
    const gradesSection = document.getElementById("grades-section");
    infoDiv.innerHTML = `
        <h2>My Courses</h2>
        <ul>
            ${studentData.courses.map(course => `<li>${course}</li>`).join('')}
        </ul>
    `;
    if (gradesSection) {
        gradesSection.style.display = "none";
    }
}

function showGrades() {
    const infoDiv = document.getElementById("personal-info");
    const gradesSection = document.getElementById("grades-section");
    infoDiv.innerHTML = "";
    if (gradesSection) {
        gradesSection.style.display = "block";
    }
}

function showAnnouncements() {
    const infoDiv = document.getElementById("personal-info");
    const gradesSection = document.getElementById("grades-section");
    infoDiv.innerHTML = "<h2>Announcements Section (coming soon)</h2>";
    if (gradesSection) {
        gradesSection.style.display = "none";
    }
}

function logout() {
    sessionStorage.clear();
    window.location.href = "/";
}

document.getElementById("personal-info").innerHTML = "";

