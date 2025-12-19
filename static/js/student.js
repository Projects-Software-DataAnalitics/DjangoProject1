
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


let studentData = JSON.parse(sessionStorage.getItem('loggedStudent'));
if (!studentData) {
    window.location.href = "/";
} else {
    const jsonPathElement = document.getElementById('student-json-path');
    const jsonPath = jsonPathElement ? jsonPathElement.dataset.path : '/static/json/students.json';
    
    fetch(jsonPath)
        .then(response => response.json())
        .then(data => {
            const currentStudent = data.find(s => s.username === studentData.username);
            if (currentStudent) {
                sessionStorage.setItem('loggedStudent', JSON.stringify(currentStudent));
                window.studentData = currentStudent;
                studentData = currentStudent;
            }
        })
        .catch(() => {
        });
}


document.getElementById("personal-info-btn").addEventListener("click", showPersonalInfo);
document.getElementById("my-courses-btn").addEventListener("click", showMyCourses);
document.getElementById("grades-btn").addEventListener("click", showGrades);
document.getElementById("announcements-btn").addEventListener("click", showAnnouncements);
document.getElementById("logout-btn").addEventListener("click", logout);


function showPersonalInfo() {
    const freshData = JSON.parse(sessionStorage.getItem('loggedStudent')) || studentData;
    const infoDiv = document.getElementById("personal-info");
    const gradesSection = document.getElementById("grades-section");
    infoDiv.innerHTML = `
        <h2>Personal Information</h2>
        <p><strong>Name:</strong> ${freshData.firstName} ${freshData.lastName}</p>
        <p><strong>Username:</strong> ${freshData.username}</p>
        <p><strong>Department:</strong> ${freshData.department}</p>
        <p><strong>Class:</strong> ${freshData.class}</p>
        <p><strong>Courses:</strong> ${(freshData.courses || []).join(", ")}</p>
    `;
    if (gradesSection) {
        gradesSection.style.display = "none";
    }
}

function showMyCourses() {
    const freshData = JSON.parse(sessionStorage.getItem('loggedStudent')) || studentData;
    const infoDiv = document.getElementById("personal-info");
    const gradesSection = document.getElementById("grades-section");
    infoDiv.innerHTML = `
        <h2>My Courses</h2>
        <ul>
            ${(freshData.courses || []).map(course => `<li>${course}</li>`).join('')}
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

function showDetails(courseName) {
    const popup = document.getElementById("popup");
    const title = document.getElementById("popup-title");
    const content = document.getElementById("popup-content");

    title.innerText = courseName;

    // Static text
    content.innerText =
        "Grade Calculation:\n\n" +
        "Midterm Exam: 33%\n" +
        "Assignments: 33%\n" +
        "Final Exam: 33%\n\n" ;

    popup.style.display = "flex";
}

function closePopup() {
    const popup = document.getElementById("popup");
    if (popup) {
        popup.style.display = "none";
    }
}


document.getElementById("personal-info").innerHTML = "";

