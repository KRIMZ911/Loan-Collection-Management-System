"""
app/routes/admin.py
====================
Admin panel blueprint for managing annual goals.

Phase E.3 — Goals admin:
    GET  /admin/                     → Landing page
    GET  /admin/goals                → List goals (filterable)
    GET, POST /admin/goals/new       → Create single goal
    GET, POST /admin/goals/bulk-new  → Create all 3 categories at once
    GET, POST /admin/goals/<id>/edit → Edit existing goal
    GET, POST /admin/goals/<id>/delete → Confirm + soft delete

All mutation routes require the "can_set_branch_goals" capability.
Soft-delete preserves the audit trail — goals are never hard-deleted.
"""

from datetime import datetime, date, timezone
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    abort, flash, session,
)
from app import db
from app.models import (
    AnnualGoal, GoalCategory, Branch, User, LoanProduct, Segment,
)
from app.services.access_control import (
    current_user, scope_branches,
    require_capability, require_login, can,
    get_dashboards, DASHBOARD_CATALOG,
)

admin_bp = Blueprint("admin", __name__)


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _get_editable_branches(user):
    """
    Return list of Branch objects this user can set goals for.
    - Executive: all branches
    - Regional director: their region's branches (via scope_branches)
    - Branch director / others: empty list (they don't have can_set_branch_goals)
    """
    if not can(user, "can_set_branch_goals"):
        return []
    return scope_branches(Branch.query, user).order_by(Branch.name).all()


def _get_visible_goals_query(user, year=None, branch_id=None, category_id=None):
    """
    Base query for goals visible to this user.
    Always excludes soft-deleted. Applies optional filters.
    """
    editable_branch_ids = [b.id for b in _get_editable_branches(user)]
    if not editable_branch_ids:
        # Nothing visible — return query that produces empty result
        return AnnualGoal.query.filter(db.false())

    q = (AnnualGoal.query
         .filter(AnnualGoal.deleted_at.is_(None))
         .filter(AnnualGoal.branch_id.in_(editable_branch_ids)))

    if year is not None:
        q = q.filter(AnnualGoal.year == year)
    if branch_id is not None:
        q = q.filter(AnnualGoal.branch_id == branch_id)
    if category_id is not None:
        q = q.filter(AnnualGoal.category_id == category_id)

    return q


def _admin_context(active_section=None):
    """Common template context for admin pages."""
    user = current_user()
    return {
        "user":                  user,
        "user_name":             user.name if user else "Зочин",
        "role_name":             user.role.name_mn if user and user.role else "",
        "active_section":        active_section,
        "can_set_branch_goals":  can(user, "can_set_branch_goals"),
        "user_dashboards":       get_dashboards(user) if user else [],
    }


def _utcnow():
    return datetime.now(timezone.utc)


# ════════════════════════════════════════════════════════════════════════════
# ROUTE 1 — Landing page
# ════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/")
@require_login
def index():
    """
    Admin landing page.
    Shows cards for each admin section the user has access to.
    """
    user = current_user()

    # Build list of available admin sections based on capabilities
    sections = []
    if can(user, "can_set_branch_goals"):
        sections.append({
            "icon":    "🎯",
            "title":   "Зорилт удирдах",
            "sub":     "Жилийн зорилт тогтоох, засах",
            "url":     url_for("admin.goals_list"),
            "color":   "#2563EB",
        })

    if can(user, "can_manage_products"):
        sections.append({
            "icon":    "📦",
            "title":   "Бүтээгдэхүүн удирдах",
            "sub":     "Зээлийн бүтээгдэхүүн нэмэх, засах",
            "url":     url_for("admin.products_list"),
            "color":   "#7C3AED",
    })

    if not sections:
        # User has no admin access at all
        abort(403)

    ctx = _admin_context()
    ctx["sections"] = sections
    return render_template("admin/index.html", **ctx)


# ════════════════════════════════════════════════════════════════════════════
# ROUTE 2 — Goals list
# ════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/goals")
@require_capability("can_set_branch_goals")
def goals_list():
    """
    List all goals visible to this user.
    Supports filters: ?year=2026&branch_id=N&category_id=N
    """
    user = current_user()

    # Parse filter params
    current_year = date.today().year
    filter_year = request.args.get("year", current_year, type=int)
    filter_branch_id = request.args.get("branch_id", type=int)
    filter_category_id = request.args.get("category_id", type=int)

    # Pre-load dropdown options
    categories = (GoalCategory.query
                  .filter_by(is_active=True)
                  .order_by(GoalCategory.sort_order, GoalCategory.id)
                  .all())
    branches = _get_editable_branches(user)
    available_years = list(range(2024, current_year + 2))

    # Build query
    q = _get_visible_goals_query(
        user,
        year=filter_year,
        branch_id=filter_branch_id,
        category_id=filter_category_id,
    )

    goals = (q.order_by(AnnualGoal.year.desc(),
                        AnnualGoal.branch_id,
                        AnnualGoal.category_id)
              .all())

    ctx = _admin_context(active_section="goals")
    ctx.update({
        "goals":              goals,
        "categories":         categories,
        "branches":           branches,
        "filter_year":        filter_year,
        "filter_branch_id":   filter_branch_id,
        "filter_category_id": filter_category_id,
        "available_years":    available_years,
    })
    return render_template("admin/goals_list.html", **ctx)


# ════════════════════════════════════════════════════════════════════════════
# ROUTE 3 — Create single goal
# ════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/goals/new", methods=["GET", "POST"])
@require_capability("can_set_branch_goals")
def goal_new():
    """
    Create one new goal.
    GET: show form (optionally pre-fill branch via ?branch_id=).
    POST: validate, create, redirect.
    """
    user = current_user()
    branches = _get_editable_branches(user)
    categories = (GoalCategory.query
                  .filter_by(is_active=True)
                  .order_by(GoalCategory.sort_order, GoalCategory.id)
                  .all())
    current_year = date.today().year
    available_years = list(range(2024, current_year + 2))

    if request.method == "POST":
        # Parse inputs
        try:
            year = int(request.form["year"])
            branch_id = int(request.form["branch_id"])
            category_id = int(request.form["category_id"])
            target_count = int(request.form["target_count"])
        except (KeyError, ValueError):
            flash("Бүх талбарыг зөв бөглөнө үү.", "error")
            return _render_goal_new_form(branches, categories, available_years)

        notes = request.form.get("notes", "").strip() or None

        # Verify branch is editable
        editable_ids = [b.id for b in branches]
        if branch_id not in editable_ids:
            abort(403)

        if target_count < 0:
            flash("Зорилтын тоо 0-ээс бага байж болохгүй.", "error")
            return _render_goal_new_form(branches, categories, available_years)

        # Check for existing non-deleted goal for same combo
        existing = (AnnualGoal.query
                    .filter_by(year=year, branch_id=branch_id, category_id=category_id)
                    .filter(AnnualGoal.deleted_at.is_(None))
                    .first())
        if existing:
            flash(
                f"Энэ салбарт {year} оны энэ ангилалд зорилт аль хэдийн тогтоогдсон байна.",
                "error",
            )
            return _render_goal_new_form(branches, categories, available_years)

        # Create
        goal = AnnualGoal(
            year=year,
            branch_id=branch_id,
            category_id=category_id,
            target_count=target_count,
            notes=notes,
            set_by_user_id=user.id,
            set_at=_utcnow(),
        )
        db.session.add(goal)
        db.session.commit()
        flash("✅ Зорилт амжилттай үүсгэлээ.", "success")
        return redirect(url_for("admin.goals_list", year=year, branch_id=branch_id))

    # GET — render form
    return _render_goal_new_form(branches, categories, available_years)


def _render_goal_new_form(branches, categories, available_years):
    """Internal helper to render the new-goal form (used by GET and error POST)."""
    prefill_branch_id = request.args.get("branch_id", type=int)
    ctx = _admin_context(active_section="goals")
    ctx.update({
        "mode":              "new",
        "form_action":       url_for("admin.goal_new"),
        "goal":              None,
        "branches":          branches,
        "categories":        categories,
        "available_years":   available_years,
        "default_year":      date.today().year,
        "prefill_branch_id": prefill_branch_id,
    })
    return render_template("admin/goal_form.html", **ctx)


# ════════════════════════════════════════════════════════════════════════════
# ROUTE 4 — Bulk create (one goal per category for a single branch+year)
# ════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/goals/bulk-new", methods=["GET", "POST"])
@require_capability("can_set_branch_goals")
def goal_bulk_new():
    """
    Create one goal per active category for a single (year, branch).
    Skips categories with empty values or where a non-deleted goal exists.
    """
    user = current_user()
    branches = _get_editable_branches(user)
    categories = (GoalCategory.query
                  .filter_by(is_active=True)
                  .order_by(GoalCategory.sort_order, GoalCategory.id)
                  .all())
    current_year = date.today().year
    available_years = list(range(2024, current_year + 2))

    if request.method == "POST":
        try:
            year = int(request.form["year"])
            branch_id = int(request.form["branch_id"])
        except (KeyError, ValueError):
            flash("Жил болон салбараа зөв сонгоно уу.", "error")
            return _render_bulk_form(branches, categories, available_years)

        # Verify branch is editable
        editable_ids = [b.id for b in branches]
        if branch_id not in editable_ids:
            abort(403)

        notes = request.form.get("notes", "").strip() or None

        created_count = 0
        skipped_count = 0

        for cat in categories:
            raw = request.form.get(f"target_{cat.id}", "").strip()
            if not raw:
                skipped_count += 1
                continue
            try:
                target = int(raw)
                if target < 0:
                    skipped_count += 1
                    continue
            except ValueError:
                skipped_count += 1
                continue

            # Check existing
            existing = (AnnualGoal.query
                        .filter_by(year=year, branch_id=branch_id, category_id=cat.id)
                        .filter(AnnualGoal.deleted_at.is_(None))
                        .first())
            if existing:
                skipped_count += 1
                continue

            goal = AnnualGoal(
                year=year,
                branch_id=branch_id,
                category_id=cat.id,
                target_count=target,
                notes=notes,
                set_by_user_id=user.id,
                set_at=_utcnow(),
            )
            db.session.add(goal)
            created_count += 1

        if created_count > 0:
            db.session.commit()
            flash(
                f"✅ {created_count} зорилт үүсгэлээ" +
                (f" ({skipped_count} алгассан)" if skipped_count else "."),
                "success",
            )
        else:
            flash("Нэг ч зорилт үүсгэгдсэнгүй. Утга оруулаагүй эсвэл аль хэдийн тогтоогдсон.", "warning")

        return redirect(url_for("admin.goals_list", year=year, branch_id=branch_id))

    return _render_bulk_form(branches, categories, available_years)


def _render_bulk_form(branches, categories, available_years):
    ctx = _admin_context(active_section="goals")
    ctx.update({
        "branches":        branches,
        "categories":      categories,
        "available_years": available_years,
        "default_year":    date.today().year,
    })
    return render_template("admin/goal_bulk_form.html", **ctx)


# ════════════════════════════════════════════════════════════════════════════
# ROUTE 5 — Edit existing goal
# ════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/goals/<int:goal_id>/edit", methods=["GET", "POST"])
@require_capability("can_set_branch_goals")
def goal_edit(goal_id):
    """Edit target_count and notes on an existing goal."""
    user = current_user()
    goal = AnnualGoal.query.get_or_404(goal_id)

    # 404 if soft-deleted
    if goal.deleted_at is not None:
        abort(404)

    # Verify branch is editable for this user
    editable_ids = [b.id for b in _get_editable_branches(user)]
    if goal.branch_id not in editable_ids:
        abort(403)

    if request.method == "POST":
        try:
            target_count = int(request.form["target_count"])
        except (KeyError, ValueError):
            flash("Зорилтын тоо буруу.", "error")
            return _render_edit_form(goal)

        if target_count < 0:
            flash("Зорилтын тоо 0-ээс бага байж болохгүй.", "error")
            return _render_edit_form(goal)

        # Update
        goal.target_count = target_count
        goal.notes = request.form.get("notes", "").strip() or None
        goal.updated_by_user_id = user.id
        # updated_at auto-updates via onupdate

        db.session.commit()
        flash("✅ Зорилт амжилттай шинэчиллээ.", "success")
        return redirect(url_for("admin.goals_list",
                                year=goal.year, branch_id=goal.branch_id))

    return _render_edit_form(goal)


def _render_edit_form(goal):
    user = current_user()
    branches = _get_editable_branches(user)
    categories = (GoalCategory.query
                  .filter_by(is_active=True)
                  .order_by(GoalCategory.sort_order, GoalCategory.id)
                  .all())
    current_year = date.today().year
    available_years = list(range(2024, current_year + 2))

    ctx = _admin_context(active_section="goals")
    ctx.update({
        "mode":            "edit",
        "form_action":     url_for("admin.goal_edit", goal_id=goal.id),
        "goal":            goal,
        "branches":        branches,
        "categories":      categories,
        "available_years": available_years,
        "default_year":    goal.year,
    })
    return render_template("admin/goal_form.html", **ctx)


# ════════════════════════════════════════════════════════════════════════════
# ROUTE 6 — Delete (with confirmation page)
# ════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/goals/<int:goal_id>/delete", methods=["GET", "POST"])
@require_capability("can_set_branch_goals")
def goal_delete(goal_id):
    """
    GET: show confirmation page.
    POST: soft-delete (set deleted_at + deleted_by_user_id).
    Goal data stays in DB forever — only filtered out of queries.
    """
    user = current_user()
    goal = AnnualGoal.query.get_or_404(goal_id)

    if goal.deleted_at is not None:
        abort(404)

    editable_ids = [b.id for b in _get_editable_branches(user)]
    if goal.branch_id not in editable_ids:
        abort(403)

    if request.method == "POST":
        goal.deleted_at = _utcnow()
        goal.deleted_by_user_id = user.id
        db.session.commit()
        flash("🗑 Зорилт устгагдлаа. (Аудит түүхэнд хадгалагдсан.)", "warning")
        return redirect(url_for("admin.goals_list",
                                year=goal.year, branch_id=goal.branch_id))

    ctx = _admin_context(active_section="goals")
    ctx["goal"] = goal
    return render_template("admin/goal_delete_confirm.html", **ctx)


# ════════════════════════════════════════════════════════════════════════════
# LOAN PRODUCTS ADMIN (Phase J.2)
# ════════════════════════════════════════════════════════════════════════════

def _get_segments_for_dropdown():
    """All segments for use in dropdowns."""
    return Segment.query.order_by(Segment.id).all()


@admin_bp.route("/products")
@require_capability("can_manage_products")
def products_list():
    """List all loan products with filters."""
    # Filter params
    filter_segment_id = request.args.get("segment_id", type=int)
    filter_active = request.args.get("active", "all")  # all / active / retired

    q = LoanProduct.query

    if filter_segment_id:
        q = q.filter(LoanProduct.segment_id == filter_segment_id)
    if filter_active == "active":
        q = q.filter(LoanProduct.is_active == True)
    elif filter_active == "retired":
        q = q.filter(LoanProduct.is_active == False)

    products = q.order_by(LoanProduct.is_active.desc(),
                          LoanProduct.category,
                          LoanProduct.name).all()

    segments = _get_segments_for_dropdown()

    ctx = _admin_context(active_section="products")
    ctx.update({
        "products":          products,
        "segments":          segments,
        "filter_segment_id": filter_segment_id,
        "filter_active":     filter_active,
    })
    return render_template("admin/products_list.html", **ctx)


@admin_bp.route("/products/new", methods=["GET", "POST"])
@require_capability("can_manage_products")
def product_new():
    """Create a new loan product."""
    user = current_user()
    segments = _get_segments_for_dropdown()

    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            category = request.form["category"].strip()
            segment_id = int(request.form["segment_id"])
        except (KeyError, ValueError):
            flash("Бүх талбарыг бөглөнө үү.", "error")
            return _render_product_form("new", segments=segments)

        if not name or not category:
            flash("Нэр болон ангилал хоосон байж болохгүй.", "error")
            return _render_product_form("new", segments=segments)

        description = request.form.get("description", "").strip() or None
        is_digital = bool(request.form.get("is_digital"))
        auto_sms_day = request.form.get("auto_sms_day", "").strip()
        auto_sms_day = int(auto_sms_day) if auto_sms_day.isdigit() else None

        product = LoanProduct(
            name=name,
            category=category,
            segment_id=segment_id,
            description=description,
            is_digital=is_digital,
            auto_sms_day=auto_sms_day,
            is_active=True,
        )
        db.session.add(product)
        db.session.commit()
        flash(f"✅ '{name}' бүтээгдэхүүн амжилттай үүсгэлээ.", "success")
        return redirect(url_for("admin.products_list"))

    return _render_product_form("new", segments=segments)


@admin_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@require_capability("can_manage_products")
def product_edit(product_id):
    """Edit an existing loan product."""
    user = current_user()
    product = LoanProduct.query.get_or_404(product_id)
    segments = _get_segments_for_dropdown()

    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            category = request.form["category"].strip()
            segment_id = int(request.form["segment_id"])
        except (KeyError, ValueError):
            flash("Бүх талбарыг бөглөнө үү.", "error")
            return _render_product_form("edit", product=product, segments=segments)

        if not name or not category:
            flash("Нэр болон ангилал хоосон байж болохгүй.", "error")
            return _render_product_form("edit", product=product, segments=segments)

        # Update
        product.name = name
        product.category = category
        product.segment_id = segment_id
        product.description = request.form.get("description", "").strip() or None
        product.is_digital = bool(request.form.get("is_digital"))

        auto_sms_day = request.form.get("auto_sms_day", "").strip()
        product.auto_sms_day = int(auto_sms_day) if auto_sms_day.isdigit() else None

        db.session.commit()
        flash(f"✅ '{name}' бүтээгдэхүүн шинэчлэгдлээ.", "success")
        return redirect(url_for("admin.products_list"))

    return _render_product_form("edit", product=product, segments=segments)


@admin_bp.route("/products/<int:product_id>/retire", methods=["GET", "POST"])
@require_capability("can_manage_products")
def product_retire(product_id):
    """Retire (soft-delete) a loan product."""
    user = current_user()
    product = LoanProduct.query.get_or_404(product_id)

    if not product.is_active:
        flash("Энэ бүтээгдэхүүн аль хэдийн идэвхгүй болсон байна.", "warning")
        return redirect(url_for("admin.products_list"))

    if request.method == "POST":
        product.is_active = False
        db.session.commit()
        flash(f"📦 '{product.name}' бүтээгдэхүүнийг идэвхгүй болголоо.", "warning")
        return redirect(url_for("admin.products_list"))

    ctx = _admin_context(active_section="products")
    ctx["product"] = product
    return render_template("admin/product_retire_confirm.html", **ctx)


@admin_bp.route("/products/<int:product_id>/restore", methods=["POST"])
@require_capability("can_manage_products")
def product_restore(product_id):
    """Re-activate a retired product."""
    user = current_user()
    product = LoanProduct.query.get_or_404(product_id)
    product.is_active = True
    db.session.commit()
    flash(f"✅ '{product.name}' бүтээгдэхүүн дахин идэвхтэй боллоо.", "success")
    return redirect(url_for("admin.products_list"))


def _render_product_form(mode, product=None, segments=None):
    """Internal helper to render the product form (new or edit)."""
    if segments is None:
        segments = _get_segments_for_dropdown()
    ctx = _admin_context(active_section="products")
    ctx.update({
        "mode":        mode,
        "form_action": url_for("admin.product_new") if mode == "new"
                       else url_for("admin.product_edit", product_id=product.id),
        "product":     product,
        "segments":    segments,
        # Common categories suggestion list
        "category_suggestions": ["Хэрэглээ", "Бизнес", "Карт", "Ипотек", "Авто"],
    })
    return render_template("admin/product_form.html", **ctx)