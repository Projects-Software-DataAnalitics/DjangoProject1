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

    const studentData = JSON.parse(sessionStorage.getItem('loggedStudent'));
    if (!studentData) {
        window.location.href = "/";
        return;
    }

    const gradesLink = document.querySelector('.sidebar a[href*="grades"]');
    if (gradesLink && studentData.username) {
        gradesLink.addEventListener('click', function(e) {
            e.preventDefault();
            const url = new URL(gradesLink.href, window.location.origin);
            url.searchParams.set('username', studentData.username);
            window.location.href = url.toString();
        });
    }

    if (window.location.pathname.includes('/grades/')) {
        const urlParams = new URLSearchParams(window.location.search);
        if (!urlParams.has('username') && studentData.username) {
            urlParams.set('username', studentData.username);
            window.location.search = urlParams.toString();
        }
    }

    const logoutLink = document.querySelector('.sidebar a[href*="logout"]');
    if (logoutLink) {
        logoutLink.addEventListener('click', function(e) {
            e.preventDefault();
            sessionStorage.clear();
            window.location.href = "/";
        });
    }
});

function showDetails(courseName) {
    const popup = document.getElementById("popup");
    const title = document.getElementById("popup-title");
    const content = document.getElementById("popup-content");

    if (!popup || !title || !content) return;

    title.innerText = courseName;

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

