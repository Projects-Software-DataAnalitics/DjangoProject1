const menuBtn = document.getElementById("menu-btn");
if (menuBtn) {
    menuBtn.addEventListener("click", toggleSidebar);
}

function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    const content = document.getElementById("content");
    if (!sidebar || !content) return;

    if (sidebar.style.width === "200px") {
        sidebar.style.width = "0";
        content.style.marginLeft = "0";
    } else {
        sidebar.style.width = "200px";
        content.style.marginLeft = "200px";
    }
}

// Basit kontrol: faculty head login yapılmamışsa ana sayfaya yönlendir
const facultyHeadDataRaw = sessionStorage.getItem("loggedFacultyHead");
if (!facultyHeadDataRaw) {
    // Eğer JSON tabanlı login kullanmıyorsan bu satırı silebilirsin
    // window.location.href = "/";
}
