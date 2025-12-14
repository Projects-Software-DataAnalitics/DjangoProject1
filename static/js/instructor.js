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

const instructorData = JSON.parse(sessionStorage.getItem('loggedInstructor'));
if (!instructorData) {
    window.location.href = "/";
}

function getCsrfToken() {
    const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
    return cookieMatch ? cookieMatch[1] : null;
}

document.getElementById("personal-info-btn").addEventListener("click", showPersonalInfo);
document.getElementById("my-courses-btn").addEventListener("click", showMyCourses);
document.getElementById("grades-btn").addEventListener("click", showGrades);
document.getElementById("announcements-btn").addEventListener("click", showAnnouncements);
document.getElementById("logout-btn").addEventListener("click", logout);

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
        <div style="margin-top: 24px;">
            <button id="view-enrollment-btn" style="padding: 10px 20px; background: #6366f1; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500;">
                📊 View Course Enrollment
            </button>
        </div>
        <div id="enrollment-section" style="margin-top: 24px; display: none;"></div>
    `;
    
    // Add event listener for enrollment button
    setTimeout(() => {
        const enrollmentBtn = document.getElementById("view-enrollment-btn");
        if (enrollmentBtn) {
            enrollmentBtn.addEventListener("click", function() {
                showCourseEnrollment();
            });
        }
    }, 50);
}

function showCourseEnrollment() {
    const enrollmentSection = document.getElementById("enrollment-section");
    enrollmentSection.style.display = "block";
    enrollmentSection.innerHTML = `
        <div style="text-align: center; padding: 20px;">
            <div class="spinner" style="border: 4px solid #f3f4f6; border-top: 4px solid #3b82f6; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
            <p style="margin-top: 12px; color: #64748b;">Loading enrollment data...</p>
        </div>
    `;

    fetch("/api/courses/enrollment/")
        .then(response => response.json())
        .then(data => {
            if (data.status === 'ok' && data.enrollment && data.enrollment.length > 0) {
                renderEnrollmentTable(data.enrollment);
            } else {
                enrollmentSection.innerHTML = `
                    <div style="padding: 20px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; color: #991b1b;">
                        <p style="font-weight: 600;">No enrollment data found</p>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error loading enrollment:', error);
            enrollmentSection.innerHTML = `
                <div style="padding: 20px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; color: #991b1b;">
                    <p style="font-weight: 600;">Error loading enrollment data</p>
                    <p>Please try again later.</p>
                </div>
            `;
        });
}

function renderEnrollmentTable(enrollment) {
    const enrollmentSection = document.getElementById("enrollment-section");
    
    // Normalize course names for comparison
    const normalizeCourseName = (name) => {
        const mappings = {
            'algorithm': 'Algorithms',
            'algortihm': 'Algorithms',
            'web programming': 'Web Programming',
            'computer architecture': 'Computer Architecture'
        };
        const lower = name.toLowerCase().trim();
        return mappings[lower] || name;
    };
    
    // Filter to show only instructor's courses (case-insensitive)
    const instructorCourses = instructorData.courses.map(c => normalizeCourseName(c).toLowerCase());
    const filteredEnrollment = enrollment.filter(item => {
        const normalizedItemCourse = normalizeCourseName(item.course_name).toLowerCase();
        return instructorCourses.includes(normalizedItemCourse);
    });
    
    if (filteredEnrollment.length === 0) {
        enrollmentSection.innerHTML = `
            <div style="padding: 20px; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; color: #0c4a6e;">
                <p style="font-weight: 600;">No students enrolled in your courses yet.</p>
            </div>
        `;
        return;
    }
    
    const courseCards = filteredEnrollment.map(item => {
        const studentRows = item.students.map(student => `
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${student.firstName} ${student.lastName}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${student.username}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${student.department || '-'}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${student.class || '-'}</td>
            </tr>
        `).join('');
        
        return `
            <div style="background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
                <h3 style="margin-bottom: 16px; color: #1f2937; font-size: 18px;">
                    ${item.course_name} 
                    <span style="color: #6b7280; font-size: 14px; font-weight: normal;">(${item.student_count} students)</span>
                </h3>
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background: #f9fafb;">
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Name</th>
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Username</th>
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Department</th>
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Class</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${studentRows}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }).join('');
    
    enrollmentSection.innerHTML = `
        <div style="margin-top: 20px;">
            <h3 style="margin-bottom: 20px; color: #1f2937;">Course Enrollment - My Courses</h3>
            ${courseCards}
        </div>
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
        <div id="grade-options-section" style="margin-top: 24px; display: none;">
            <h3 style="margin-bottom: 16px; color: #1f2937; font-size: 18px;">Select an option:</h3>
            <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                <button id="csv-upload-btn" style="padding: 12px 24px; background: #3b82f6; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500; font-size: 14px;">
                    📄 CSV Dosyası Yükle
                </button>
                <button id="manual-entry-btn" style="padding: 12px 24px; background: #10b981; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500; font-size: 14px;">
                    ✏️ Manuel Not Girişi
                </button>
                <button id="view-grades-btn" style="padding: 12px 24px; background: #8b5cf6; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500; font-size: 14px;">
                    👁️ Verilen Notları Görüntüle
                </button>
            </div>
        </div>
        <div id="file-upload-section" style="margin-top: 24px; display: none;"></div>
        <div id="manual-entry-section" style="margin-top: 24px; display: none;"></div>
        <div id="view-grades-section" style="margin-top: 24px; display: none;"></div>
        <div id="upload-status" class="upload-status" style="margin-top: 16px;"></div>
    `;
    
    // Add event listeners after DOM is updated
    setTimeout(() => {
        const courseSelect = document.getElementById("course-select");
        if (courseSelect) {
            courseSelect.addEventListener("change", function() {
                const selectedCourse = this.value;
                const gradeOptionsSection = document.getElementById("grade-options-section");
                const fileUploadSection = document.getElementById("file-upload-section");
                const manualEntrySection = document.getElementById("manual-entry-section");
                const viewGradesSection = document.getElementById("view-grades-section");
                
                if (selectedCourse) {
                    if (gradeOptionsSection) gradeOptionsSection.style.display = "block";
                    if (fileUploadSection) fileUploadSection.style.display = "none";
                    if (manualEntrySection) manualEntrySection.style.display = "none";
                    if (viewGradesSection) viewGradesSection.style.display = "none";
                    refreshUploadStatus(selectedCourse);
                } else {
                    if (gradeOptionsSection) gradeOptionsSection.style.display = "none";
                    if (fileUploadSection) fileUploadSection.style.display = "none";
                    if (manualEntrySection) manualEntrySection.style.display = "none";
                    if (viewGradesSection) viewGradesSection.style.display = "none";
                    refreshUploadStatus(null);
                }
            });
        }

        // Button event listeners
        const csvBtn = document.getElementById("csv-upload-btn");
        const manualBtn = document.getElementById("manual-entry-btn");
        const viewBtn = document.getElementById("view-grades-btn");
        
        if (csvBtn) {
            csvBtn.addEventListener("click", function() {
                const selectedCourse = document.getElementById("course-select").value;
                if (selectedCourse) {
                    const fileUploadSection = document.getElementById("file-upload-section");
                    const manualEntrySection = document.getElementById("manual-entry-section");
                    const viewGradesSection = document.getElementById("view-grades-section");
                    if (fileUploadSection) fileUploadSection.style.display = "block";
                    if (manualEntrySection) manualEntrySection.style.display = "none";
                    if (viewGradesSection) viewGradesSection.style.display = "none";
                    updateFileUploadSection(selectedCourse);
                }
            });
        }
        
        if (manualBtn) {
            manualBtn.addEventListener("click", function() {
                const selectedCourse = document.getElementById("course-select").value;
                if (selectedCourse) {
                    const fileUploadSection = document.getElementById("file-upload-section");
                    const manualEntrySection = document.getElementById("manual-entry-section");
                    const viewGradesSection = document.getElementById("view-grades-section");
                    if (fileUploadSection) fileUploadSection.style.display = "none";
                    if (manualEntrySection) manualEntrySection.style.display = "block";
                    if (viewGradesSection) viewGradesSection.style.display = "none";
                    showManualGradeEntry(selectedCourse);
                }
            });
        }
        
        if (viewBtn) {
            viewBtn.addEventListener("click", function() {
                const selectedCourse = document.getElementById("course-select").value;
                if (selectedCourse) {
                    const fileUploadSection = document.getElementById("file-upload-section");
                    const manualEntrySection = document.getElementById("manual-entry-section");
                    const viewGradesSection = document.getElementById("view-grades-section");
                    if (fileUploadSection) fileUploadSection.style.display = "none";
                    if (manualEntrySection) manualEntrySection.style.display = "none";
                    if (viewGradesSection) viewGradesSection.style.display = "block";
                    showInstructorGrades(selectedCourse);
                }
            });
        }
    }, 50);

    refreshUploadStatus(null);
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

function showManualGradeEntry(course) {
    const manualEntrySection = document.getElementById("manual-entry-section");
    manualEntrySection.innerHTML = `
        <div style="text-align: center; padding: 20px;">
            <div class="spinner" style="border: 4px solid #f3f4f6; border-top: 4px solid #3b82f6; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
            <p style="margin-top: 12px; color: #64748b;">Loading students...</p>
        </div>
    `;

    // Fetch students for this course
    const encodedCourse = encodeURIComponent(course);
    fetch(`/api/course/${encodedCourse}/students/`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'ok' && data.students && data.students.length > 0) {
                renderManualGradeForm(course, data.students);
            } else {
                manualEntrySection.innerHTML = `
                    <div style="padding: 20px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; color: #991b1b;">
                        <p style="font-weight: 600; margin-bottom: 8px;">No students found</p>
                        <p>No students are enrolled in ${course} course.</p>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error loading students:', error);
            manualEntrySection.innerHTML = `
                <div style="padding: 20px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; color: #991b1b;">
                    <p style="font-weight: 600;">Error loading students</p>
                    <p>Please try again later.</p>
                </div>
            `;
        });
}

function renderManualGradeForm(course, students) {
    const manualEntrySection = document.getElementById("manual-entry-section");
    
    const tableRows = students.map((student, index) => `
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                <strong>${student.firstName} ${student.lastName}</strong><br>
                <small style="color: #6b7280;">${student.username}</small>
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                <input type="number" 
                       id="midterm-${index}" 
                       class="grade-input" 
                       min="0" 
                       max="100" 
                       step="0.1"
                       placeholder="0-100"
                       style="width: 100px; padding: 6px; border: 1px solid #d1d5db; border-radius: 4px;">
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                <input type="number" 
                       id="assignment-${index}" 
                       class="grade-input" 
                       min="0" 
                       max="100" 
                       step="0.1"
                       placeholder="0-100"
                       style="width: 100px; padding: 6px; border: 1px solid #d1d5db; border-radius: 4px;">
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                <input type="number" 
                       id="final-${index}" 
                       class="grade-input" 
                       min="0" 
                       max="100" 
                       step="0.1"
                       placeholder="0-100"
                       style="width: 100px; padding: 6px; border: 1px solid #d1d5db; border-radius: 4px;">
            </td>
        </tr>
    `).join('');

    manualEntrySection.innerHTML = `
        <div style="background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px;">
            <h3 style="margin-bottom: 20px; color: #1f2937;">Manual Grade Entry - ${course}</h3>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #f9fafb;">
                            <th style="padding: 12px; text-align: left; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Student</th>
                            <th style="padding: 12px; text-align: center; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Midterm</th>
                            <th style="padding: 12px; text-align: center; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Assignment</th>
                            <th style="padding: 12px; text-align: center; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Final</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tableRows}
                    </tbody>
                </table>
            </div>
            <div style="margin-top: 24px; display: flex; gap: 12px; justify-content: flex-end;">
                <button id="cancel-manual-btn" style="padding: 10px 20px; background: #6b7280; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500;">
                    Cancel
                </button>
                <button id="save-manual-grades-btn" style="padding: 10px 20px; background: #10b981; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500;">
                    💾 Save Grades
                </button>
            </div>
            <div id="manual-save-status" style="margin-top: 16px;"></div>
        </div>
    `;

    // Store students data for saving
    manualEntrySection.dataset.students = JSON.stringify(students);
    manualEntrySection.dataset.course = course;

    // Event listeners
    document.getElementById("cancel-manual-btn").addEventListener("click", function() {
        document.getElementById("manual-entry-section").style.display = "none";
    });

    document.getElementById("save-manual-grades-btn").addEventListener("click", function() {
        saveManualGrades(course, students);
    });
}

function saveManualGrades(course, students) {
    const statusEl = document.getElementById("manual-save-status");
    const grades = [];

    // Collect all grades
    students.forEach((student, index) => {
        const midterm = document.getElementById(`midterm-${index}`).value;
        const assignment = document.getElementById(`assignment-${index}`).value;
        const final = document.getElementById(`final-${index}`).value;

        grades.push({
            student_username: student.username,
            midterm: midterm || 0,
            assignment: assignment || 0,
            final: final || 0
        });
    });

    statusEl.innerHTML = '<p style="color: #3b82f6;">Saving grades...</p>';

    fetch("/api/grades/manual/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken() || ""
        },
        body: JSON.stringify({
            course_name: course,
            grades: grades
        }),
        credentials: "same-origin"
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === "ok") {
            statusEl.innerHTML = `<p style="color: #10b981; font-weight: 600;">✓ ${data.message}</p>`;
            // Clear inputs after successful save
            setTimeout(() => {
                students.forEach((student, index) => {
                    document.getElementById(`midterm-${index}`).value = "";
                    document.getElementById(`assignment-${index}`).value = "";
                    document.getElementById(`final-${index}`).value = "";
                });
            }, 2000);
        } else {
            statusEl.innerHTML = `<p style="color: #ef4444;">✗ Error: ${data.error || "Failed to save grades"}</p>`;
        }
    })
    .catch(error => {
        console.error('Error saving grades:', error);
        statusEl.innerHTML = `<p style="color: #ef4444;">✗ Error saving grades. Please try again.</p>`;
    });
}

function showInstructorGrades(course) {
    const viewGradesSection = document.getElementById("view-grades-section");
    viewGradesSection.innerHTML = `
        <div style="text-align: center; padding: 20px;">
            <div class="spinner" style="border: 4px solid #f3f4f6; border-top: 4px solid #3b82f6; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
            <p style="margin-top: 12px; color: #64748b;">Loading grades...</p>
        </div>
    `;

    const encodedCourse = encodeURIComponent(course);
    fetch(`/api/instructor/${encodedCourse}/grades/`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'ok' && data.grades && data.grades.length > 0) {
                renderInstructorGradesTable(course, data.grades);
            } else {
                viewGradesSection.innerHTML = `
                    <div style="padding: 20px; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; color: #0c4a6e;">
                        <p style="font-weight: 600; margin-bottom: 8px;">No grades found</p>
                        <p>No grades have been entered for ${course} course yet.</p>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error loading grades:', error);
            viewGradesSection.innerHTML = `
                <div style="padding: 20px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; color: #991b1b;">
                    <p style="font-weight: 600;">Error loading grades</p>
                    <p>Please try again later.</p>
                </div>
            `;
        });
}

function renderInstructorGradesTable(course, grades) {
    const viewGradesSection = document.getElementById("view-grades-section");
    
    const tableRows = grades.map(grade => `
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                <strong>${grade.student_username}</strong>
            </td>
            <td style="padding: 12px; text-align: center; border-bottom: 1px solid #e5e7eb;">${grade.midterm}</td>
            <td style="padding: 12px; text-align: center; border-bottom: 1px solid #e5e7eb;">${grade.assignment}</td>
            <td style="padding: 12px; text-align: center; border-bottom: 1px solid #e5e7eb;">${grade.final}</td>
        </tr>
    `).join('');

    viewGradesSection.innerHTML = `
        <div style="background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px;">
            <h3 style="margin-bottom: 20px; color: #1f2937;">Grades Given - ${course}</h3>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #f9fafb;">
                            <th style="padding: 12px; text-align: left; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Student Username</th>
                            <th style="padding: 12px; text-align: center; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Midterm</th>
                            <th style="padding: 12px; text-align: center; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Assignment</th>
                            <th style="padding: 12px; text-align: center; border-bottom: 2px solid #e5e7eb; color: #374151; font-weight: 600;">Final</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tableRows}
                    </tbody>
                </table>
            </div>
            <div style="margin-top: 16px;">
                <button id="close-view-grades-btn" style="padding: 10px 20px; background: #6b7280; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500;">
                    Close
                </button>
            </div>
        </div>
    `;

    document.getElementById("close-view-grades-btn").addEventListener("click", function() {
        document.getElementById("view-grades-section").style.display = "none";
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

document.getElementById("personal-info").innerHTML = "";


