
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
    
    // Clear personal info and show loading state
    infoDiv.innerHTML = "";
    if (gradesSection) {
        gradesSection.style.display = "block";
    }
    
    // Get student username from sessionStorage
    const studentData = JSON.parse(sessionStorage.getItem('loggedStudent'));
    if (!studentData || !studentData.username) {
        if (gradesSection) {
            gradesSection.innerHTML = '<p class="no-grades-message">Unable to load grades. Please login again.</p>';
        }
        return;
    }
    
    // Show loading message
    const gradesTableBody = gradesSection.querySelector('.grades-table tbody');
    if (gradesTableBody) {
        gradesTableBody.innerHTML = '<tr><td colspan="5" style="text-align: center;">Loading grades...</td></tr>';
    } else {
        gradesSection.innerHTML = '<p class="no-grades-message">Loading grades...</p>';
    }
    
    // Fetch grades from API
    const username = encodeURIComponent(studentData.username);
    fetch(`/api/student/${username}/grades/`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'ok' && data.grades && data.grades.length > 0) {
                // Update the grades table
                updateGradesTable(data.grades);
            } else {
                // No grades available
                if (gradesSection) {
                    const existingTable = gradesSection.querySelector('.grades-table');
                    if (existingTable) {
                        const tbody = existingTable.querySelector('tbody');
                        if (tbody) {
                            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #64748b;">No grades available yet.</td></tr>';
                        }
                    } else {
                        gradesSection.innerHTML = '<p class="no-grades-message">No grades available yet.</p>';
                    }
                }
            }
        })
        .catch(error => {
            console.error('Error fetching grades:', error);
            if (gradesSection) {
                gradesSection.innerHTML = '<p class="no-grades-message" style="color: #b91c1c;">Error loading grades. Please try again later.</p>';
            }
        });
}

function updateGradesTable(grades) {
    const gradesSection = document.getElementById("grades-section");
    if (!gradesSection) return;
    
    // Check if table exists, if not create it
    let table = gradesSection.querySelector('.grades-table');
    if (!table) {
        gradesSection.innerHTML = `
            <section class="grades-section">
                <h2>Your Grades</h2>
                <table class="grades-table">
                    <thead>
                        <tr>
                            <th>Course</th>
                            <th>Midterm</th>
                            <th>Assignment</th>
                            <th>Final</th>
                            <th>Details</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </section>
        `;
        table = gradesSection.querySelector('.grades-table');
    }
    
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    
    // Populate table with grades
    tbody.innerHTML = grades.map(grade => `
        <tr>
            <td>${grade.course_name}</td>
            <td>${grade.midterm}</td>
            <td>${grade.assignment}</td>
            <td>${grade.final}</td>
            <td>
                <button onclick="showDetails('${grade.course_name}')">
                    Show Details
                </button>
            </td>
        </tr>
    `).join('');
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

