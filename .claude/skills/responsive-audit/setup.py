"""Emit sessions + a URL map for the responsive audit. Run via:
    venv/bin/python manage.py shell < setup.py | grep AUDITJSON | sed 's/AUDITJSON//' > audit.json

Does NOT mutate data — it only creates login sessions and reads existing content.
Pages whose data doesn't exist are omitted (printed to stderr-ish notes).

To cover article / learning-path / instructor pages when that data is missing,
uncomment make_fixtures() below, run, audit, then DELETE the fixtures afterwards
(the local DB is a copy of prod — never leave test rows). A teardown snippet is
included at the bottom.
"""
import json
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from learning.models import (Course, Category, Module, Lesson, LearningPath,
                             Quiz, QuizAttempt, Certificate)

U = get_user_model()
notes = []


def make_session(user):
    s = SessionStore()
    s["_auth_user_id"] = str(user.pk)
    s["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    s["_auth_user_hash"] = user.get_session_auth_hash()
    s.create()
    return s.session_key


regular = U.objects.filter(is_staff=False).first() or U.objects.first()
staff = U.objects.filter(is_staff=True).first() or regular

course = Course.objects.filter(status="published").first()
module = course.modules.first()
lesson = module.lessons.first()
cat = Category.objects.first()

urls = {
    "home": "/",
    "catalog": "/malaka/",
    "category": f"/malaka/kategoriya/{cat.slug}/" if cat else None,
    "search": "/malaka/qidiruv/?q=html",
    "course_detail": f"/malaka/{course.slug}/",
    "module_detail": f"/malaka/{course.slug}/{module.slug}/",
    "lesson_video": f"/malaka/{course.slug}/{module.slug}/{lesson.slug}/",
    "learning_paths": "/malaka/yonalishlar/",
    "leaderboard": "/malaka/reyting/",
    "wishlist": "/malaka/sevimlilar/",
    "my_learning": "/malaka/mening-kurslarim/",
    "profile": "/users/profile/",
    "admin_panel": "/users/admin/",
    "login": "/users/login/",
    "login_password": "/users/kirish/parol/",
    "set_password": "/users/parol-ornatish/",
}

art = Lesson.objects.filter(lesson_type="article").first()
if art:
    urls["lesson_article"] = f"/malaka/{art.module.course.slug}/{art.module.slug}/{art.slug}/"
else:
    notes.append("no article lesson -> lesson_article skipped")

lp = LearningPath.objects.first()
if lp:
    urls["learning_path_detail"] = f"/malaka/yonalish/{lp.slug}/"
else:
    notes.append("no learning path -> learning_path_detail skipped")

inst_course = Course.objects.exclude(instructor__isnull=True).first()
if inst_course:
    urls["instructor"] = f"/malaka/oqituvchi/{inst_course.instructor.username}/"
else:
    notes.append("no instructor FK -> instructor page skipped")

cert = Certificate.objects.first()
cert_owner = cert.user if cert else regular
if cert:
    code = getattr(cert, "verification_code", None) or getattr(cert, "code", None)
    urls["certificate"] = f"/malaka/{cert.course.slug}/sertifikat/"
    if code:
        urls["public_certificate"] = f"/malaka/sertifikat/tekshirish/{code}/"
else:
    notes.append("no certificate -> certificate pages skipped")

qa = QuizAttempt.objects.filter(completed_at__isnull=False).first()
quiz_owner = qa.user if qa else regular  # quiz_result is scoped to the attempt's owner
if qa:
    ql = qa.quiz.lesson
    urls["quiz_detail"] = f"/malaka/{ql.module.course.slug}/{ql.module.slug}/{ql.slug}/test/{qa.quiz.id}/"
    urls["quiz_result"] = (f"/malaka/{ql.module.course.slug}/{ql.module.slug}/{ql.slug}"
                           f"/test/{qa.quiz.id}/urinish/{qa.id}/natija/")
else:
    notes.append("no completed quiz attempt -> quiz pages skipped")

data = {
    "sessions": {
        "user": make_session(regular),
        "staff": make_session(staff),
        "cert_owner": make_session(cert_owner),
        "quiz_owner": make_session(quiz_owner),
    },
    "urls": urls,
    "auth_map": {
        "wishlist": "user", "my_learning": "user", "profile": "user",
        "set_password": "user", "learning_path_detail": "user",
        "admin_panel": "staff", "certificate": "cert_owner",
        "quiz_detail": "quiz_owner", "quiz_result": "quiz_owner",
    },
    "notes": notes,
}
print("AUDITJSON" + json.dumps(data))

# ── Optional full-coverage fixtures (LOCAL DB ONLY — delete afterwards) ──────────
# def make_fixtures():
#     from learning.models import LearningPathCourse
#     m = Course.objects.filter(status="published").first().modules.first()
#     Lesson.objects.get_or_create(slug="audit-maqola-dars", defaults=dict(
#         module=m, title="Audit Maqola", lesson_type="article", order=999,
#         description="# H1\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```py\nprint('x')\n```"))
#     lp, _ = LearningPath.objects.get_or_create(slug="audit-yonalishi",
#         defaults=dict(title="Audit Yo'nalishi", description="audit"))
#     for i, c in enumerate(Course.objects.filter(status="published")[:3]):
#         LearningPathCourse.objects.get_or_create(path=lp, course=c, defaults={"order": i})
#     c = Course.objects.filter(status="published").first()
#     if not c.instructor:
#         c.instructor = U.objects.filter(is_staff=True).first(); c.save(update_fields=["instructor"])
# Teardown after auditing:
#     Lesson.objects.filter(slug="audit-maqola-dars").delete()
#     LearningPath.objects.filter(slug="audit-yonalishi").delete()
#     # reset the instructor FK you set, and delete leftover sessions:
#     from django.contrib.sessions.models import Session; Session.objects.all().delete()
