DELETE FROM core_announcement 
WHERE sender_id = (SELECT id FROM auth_user WHERE username = 'michael.brown');

DELETE FROM core_announcement 
WHERE receiver_id = (SELECT id FROM auth_user WHERE username = 'michael.brown');

DELETE FROM core_grade 
WHERE student_id = (SELECT id FROM core_student WHERE username = 'michael.brown');

DELETE FROM core_student_courses 
WHERE student_id = (SELECT id FROM core_student WHERE username = 'michael.brown');

DELETE FROM core_userprofile_courses 
WHERE userprofile_id = (
    SELECT id FROM core_userprofile 
    WHERE user_id = (SELECT id FROM auth_user WHERE username = 'michael.brown')
);

DELETE FROM core_student WHERE username = 'michael.brown';

DELETE FROM core_userprofile 
WHERE user_id = (SELECT id FROM auth_user WHERE username = 'michael.brown');

DELETE FROM auth_user WHERE username = 'michael.brown';

