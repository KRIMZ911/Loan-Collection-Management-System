"""
app/routes/dashboard.py
========================
Phase B unified routing:
    /menu                       → Card menu for users with 2+ dashboards
    /dashboard/<dashboard_type> → The actual dashboard (4 universal types)
    /case/<loan_id>             → Case detail page

The 4 universal dashboard types are: bank, regional, branches, loans.
For Phase B only `loans` is fully built; the others are stubs that will be
filled in during Phases C, D, E.

All scope filtering goes through access_control.scope_loans() etc. — this
file does NOT do any geographic / segment filtering manually.
"""
import math
from types import SimpleNamespace
from flask import (
    Blueprint, render_template, render_template_string,
    redirect, url_for, request, abort,
)
from sqlalchemy import func

from app import db
from app.models import (
    User, Borrower, Loan, ContactLog, CaseTransfer,
    OutsourcingAssignment, Branch,
    LoanStatus,
)
from app.services.scoring import score_cases, RISK_LEVELS
from app.services.access_control import (
    current_user,
    get_dashboards,
    get_default_dashboard,
    can_access_dashboard,
    scope_loans,
    can_view_loan,
    mask_personal_info,
    require_login,
    require_dashboard,
    DASHBOARD_CATALOG,
    get_scope_label,
)

dashboard_bp = Blueprint("dashboard", __name__)


# Pagination — rows per page for list dashboards
PER_PAGE = 50


# ════════════════════════════════════════════════════════════════════════════
# CONTEXT + HELPERS
# ════════════════════════════════════════════════════════════════════════════

def get_base_context(active_dashboard=None):
    """Shared template context — pulled from the logged-in user."""
    user = current_user()
    return {
        "user":               user,
        "user_name":          user.name if user else "Зочин",
        "role_name":          user.role.name_mn if user and user.role else "",
        "role_sub":           user.branch.name if user and user.branch else "",
        "active_dashboard":   active_dashboard,
        "user_dashboards":    _menu_items_for(user),
        "risk_levels":        RISK_LEVELS,
    }


def _menu_items_for(user):
    """Return a list of dashboard menu items for the user, in display order."""
    items = []
    for dash_type in get_dashboards(user):
        meta = DASHBOARD_CATALOG.get(dash_type, {})
        items.append({
            "type":     dash_type,
            "icon":     meta.get("icon", ""),
            "label_mn": meta.get("label_mn", dash_type),
            "sub_mn":   meta.get("sub_mn", ""),
            "color":    meta.get("color", "#64748B"),
            "url":      url_for("dashboard.dashboard", dashboard_type=dash_type),
        })
    return items


def _build_pagination(page, total_count):
    """Build pagination metadata dict for templates."""
    total_pages = max(1, math.ceil(total_count / PER_PAGE))
    page = max(1, min(page, total_pages))
    return {
        "page":         page,
        "per_page":     PER_PAGE,
        "total":        total_count,
        "total_pages":  total_pages,
        "has_prev":     page > 1,
        "has_next":     page < total_pages,
        "prev_page":    max(1, page - 1),
        "next_page":    min(total_pages, page + 1),
        "start_row":    (page - 1) * PER_PAGE + 1 if total_count > 0 else 0,
        "end_row":      min(page * PER_PAGE, total_count),
    }


# ── SimpleNamespace wrappers: new model attrs → old template names ─────────

def _w_case(loan):
    return SimpleNamespace(
        id=loan.id,
        days_overdue=loan.delinquency_days or 0,
        overdue_amount=float(loan.amount_overdue or 0),
        status=loan.status.value if loan.status else "active",
        updated_at=loan.updated_at,
    )

def _w_loan(loan):
    return SimpleNamespace(
        id=loan.id,
        amount=float(loan.amount_original or 0),
        balance=float(loan.amount_outstanding or 0),
        loan_number=loan.loan_account_number,
        product_type=loan.loan_product.name if loan.loan_product else None,
        branch=loan.branch.name if loan.branch else "—",
        interest_rate=float(loan.interest_rate or 0),
        disbursement_date=loan.disbursement_date,
        maturity_date=loan.maturity_date,
    )

def _w_borrower(borrower, hide=False):
    if hide:
        return SimpleNamespace(
            name="***", register_no="***", phone="***",
            email="***", address="***",
        )
    return SimpleNamespace(
        name=f"{borrower.last_name} {borrower.first_name}",
        register_no=borrower.register_number,
        phone=borrower.phone_primary,
        email=borrower.email,
        address=borrower.address_residential,
    )

def _w_risk(risk_info):
    rl = risk_info.get("risk_level", {})
    return SimpleNamespace(
        score=risk_info.get("score", 0),
        css_class=rl.get("css_class", "risk-low"),
        emoji=rl.get("emoji", ""),
        label_mn=rl.get("label_mn", ""),
        color=rl.get("color", "#16A34A"),
        level=rl.get("level", "low"),
    )

def _w_action(cl):
    return SimpleNamespace(
        created_at=cl.contact_date,
        action_type=cl.contact_type.value if cl.contact_type else "note",
        outcome="no_answer" if not cl.was_reached else "contacted",
        notes=cl.notes or "",
    )

def _w_transfer(t):
    return SimpleNamespace(
        transfer_date=t.transfer_date,
        to_entity=t.to_entity,
        reason=t.reason or "",
        status=t.status.value if t.status else "pending",
    )

def _pack_scored(scored):
    return [(_w_case(l), _w_loan(l), _w_borrower(b), _w_risk(r))
            for l, b, r in scored]

def _build_kpis(scored):
    total = len(scored)
    total_amount = sum(float(l.amount_overdue or 0) for l, b, r in scored)
    high_risk = sum(1 for l, b, r in scored if r.get("score", 0) >= 50)
    return [
        {"label": "Энэ хуудсанд", "value": total,
         "sub": "Зөрчилтэй зээл"},
        {"label": "Энэ хуудсын дүн", "value": f"{total_amount:,.0f} ₮",
         "sub": "Хэтэрсэн өр"},
        {"label": "Өндөр эрсдэл", "value": high_risk,
         "sub": "Эрсдэл 50+"},
    ]


# ════════════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════════════

@dashboard_bp.route("/menu")
@require_login
def menu():
    """Show the menu of dashboards available to this user."""
    user = current_user()
    items = _menu_items_for(user)

    # If somehow they only have one, skip the menu
    if len(items) <= 1:
        if items:
            return redirect(items[0]["url"])
        abort(403)

    ctx = get_base_context()
    ctx["menu_items"] = items
    return render_template("menu.html", **ctx)


@dashboard_bp.route("/dashboard/<dashboard_type>")
@require_login
def dashboard(dashboard_type):
    """Universal dashboard router — dispatches to the right builder."""
    user = current_user()

    if not can_access_dashboard(user, dashboard_type):
        abort(403)

    builders = {
    "bank":     _build_bank,
    "regional": _build_regional,
    "branch":   _build_branch,         # ← renamed key
    "loans":    _build_loans,
    }
    builder = builders.get(dashboard_type)
    if builder is None:
        abort(404)
    return builder()


@dashboard_bp.route("/case/<int:loan_id>")
@require_login
def case_detail(loan_id):
    """Case detail page — works for any dashboard type."""
    user = current_user()
    loan = Loan.query.get_or_404(loan_id)

    if not can_view_loan(user, loan):
        abort(403)

    borrower = Borrower.query.get(loan.borrower_id)
    hide = mask_personal_info(user)
    contacts = (ContactLog.query
                .filter_by(loan_id=loan.id)
                .order_by(ContactLog.contact_date.desc())
                .limit(50).all())
    transfers = CaseTransfer.query.filter_by(loan_id=loan.id).all()
    scored = score_cases([(loan, borrower)])
    ri = scored[0][2] if scored else {}

    ctx = get_base_context()
    ctx.update({
        "loan":      _w_loan(loan),
        "case":      _w_case(loan),
        "borrower":  _w_borrower(borrower, hide=hide) if borrower
                     else SimpleNamespace(name="—", register_no="—",
                                          phone="—", email="—", address="—"),
        "risk":      _w_risk(ri),
        "actions":   [_w_action(c) for c in contacts],
        "transfers": [_w_transfer(t) for t in transfers],
    })
    return render_template("dashboard/case_detail.html", **ctx)


# ════════════════════════════════════════════════════════════════════════════
# DASHBOARD BUILDERS
# ════════════════════════════════════════════════════════════════════════════

def _build_loans():
    """
    Loans dashboard — universal, scope-aware, with smart search + filters.
    """
    user = current_user()
    page = request.args.get("page", 1, type=int)

    # 🎯 Step 1: Scope (security) — what data can this user see at all
    base_q = scope_loans(Loan.query, user)

    # 🎯 Step 2: Apply user's search + filters from URL params
    from app.services.loan_search import (
        apply_search_and_filters,
        build_filter_chips,
        get_filter_options,
    )
    filtered_q, parsed_search = apply_search_and_filters(base_q, request.args)

    # Default behavior: show only delinquent if no specific filter narrows it
    if not request.args.get("days_min") and not request.args.get("status"):
        filtered_q = filtered_q.filter(Loan.delinquency_days > 0)

    # 🎯 Step 3: Paginate
    total = filtered_q.count()
    loans = (filtered_q.order_by(Loan.delinquency_days.desc())
                       .offset((page - 1) * PER_PAGE)
                       .limit(PER_PAGE).all())

    rows = [(l, l.borrower) for l in loans]
    scored = score_cases(rows)
    cases = _pack_scored(scored)

    # 🎯 Step 4: Get dropdown options + active chips for the UI
    filter_opts = get_filter_options(user)
    chips = build_filter_chips(
        request.args.to_dict(),
        parsed_search,
        filter_opts["branches_dict"],
        filter_opts["products_dict"],
    )

    # 🎯 Step 5: Build full context
    ctx = get_base_context(active_dashboard="loans")
    ctx.update({
        # data
        "cases":            cases,
        "kpis":             _build_kpis(scored),
        "pagination":       _build_pagination(page, total),
        "hide_pii":         mask_personal_info(user),
        # chrome
        "dashboard_meta":   DASHBOARD_CATALOG.get("loans", {}),
        "scope_label":      get_scope_label(user),
        "show_back_button": len(get_dashboards(user)) > 1,
        "total_results":    total,
        # search + filters
        "parsed_search":    parsed_search,
        "filter_chips":     chips,
        "filter_opts":      filter_opts,
        "request_args":     request.args.to_dict(),
    })
    return render_template("dashboard/loans.html", **ctx)

# ─── STUBS — Phases C, D, E will fill these in ─────────────────────────────

_STUB_TEMPLATE = """
<!DOCTYPE html>
<html lang="mn">
<head>
    <meta charset="UTF-8">
    <title>{{ title }} — CMS</title>
    {{ url_for('static', filename='css/style.css') }}
    <style>
        .stub-page { max-width: 720px; margin: 80px auto; padding: 32px;
                     text-align: center; }
        .stub-page h1 { font-size: 48px; margin-bottom: 16px; }
        .stub-page p { color: #64748B; font-size: 18px; }
        .stub-back { display: inline-block; margin-top: 24px;
                     padding: 10px 24px; background: #2563EB;
                     color: white; border-radius: 8px;
                     text-decoration: none; }
    </style>
</head>
<body>
<div class="stub-page">
    <h1>{{ icon }} {{ title }}</h1>
    <p>{{ message }}</p>
    <a href="{{ back_url }}" class="stub-back">← Буцах</a>
</div>
</body>
</html>
"""


@require_dashboard("regional")        # ← changed from "branches"
def _build_regional():                # ← renamed from _

    """
    Branches dashboard — sortable comparison table + attention widgets.
    All data comes through scope-aware widget functions in branch_stats.
    """
    from app.services.branch_stats import (
        widget_branches_kpi_summary,
        widget_branches_comparison_table,
        widget_top_risk_branches,
        get_all_attention_signals,
    )

    user = current_user()

    # Sort params from URL (?sort=amount&dir=desc)
    sort_by  = request.args.get("sort", "amount")
    sort_dir = request.args.get("dir",  "desc")

    # Pull data from all widgets
    kpis            = widget_branches_kpi_summary(user)
    branch_rows     = widget_branches_comparison_table(user, sort_by, sort_dir)
    top_risk        = widget_top_risk_branches(user, limit=5)
    attention       = get_all_attention_signals(user)

    ctx = get_base_context(active_dashboard="regional")
    ctx.update({
        # chrome
        "dashboard_meta":   DASHBOARD_CATALOG.get("regional", {}),
        "scope_label":      get_scope_label(user),
        "show_back_button": len(get_dashboards(user)) > 1,
        # data
        "kpis":             kpis,
        "branch_rows":      branch_rows,
        "top_risk":         top_risk,
        "attention":        attention,
        # state
        "sort_by":          sort_by,
        "sort_dir":         sort_dir,
    })
    return render_template("dashboard/regional.html", **ctx)

@require_dashboard("branch")
def _build_branch():
    """
    Branch dashboard — single-branch detail view.

    Scope rules:
      - Branch worker/manager: auto-uses their own branch (user.branch_id)
      - Regional director/executive: picks via ?branch_id=N param
      - If no branch_id and user has no own branch → branch picker
    """
    from app.services.branch_stats import (
        widget_branch_summary_kpis,
        widget_branch_goals_progress,
        widget_branch_worker_performance,
        widget_branch_recent_activity,
        _verify_branch_access,
    )
    from app.services.access_control import scope_branches, can

    user = current_user()

    # Determine which branch to show
    branch_id = request.args.get("branch_id", type=int)
    if branch_id is None:
        # Default to user's own branch
        branch_id = user.branch_id

    # If still no branch (e.g. regional director hasn't picked one) — show picker
    if branch_id is None:
        visible_branches = scope_branches(Branch.query, user).order_by(Branch.name).all()
        ctx = get_base_context(active_dashboard="branch")
        ctx.update({
            "dashboard_meta":   DASHBOARD_CATALOG.get("branch", {}),
            "scope_label":      get_scope_label(user),
            "show_back_button": len(get_dashboards(user)) > 1,
            "show_picker":      True,
            "visible_branches": visible_branches,
        })
        return render_template("dashboard/branch.html", **ctx)

    # Try to access the branch — 403 if not allowed
    try:
        _verify_branch_access(user, branch_id)
    except ValueError:
        abort(403)

    # Pull data from all widgets
    summary    = widget_branch_summary_kpis(user, branch_id)
    goals      = widget_branch_goals_progress(user, branch_id)
    workers    = widget_branch_worker_performance(user, branch_id)
    activity   = widget_branch_recent_activity(user, branch_id, limit=10)

    # For "Зорилт засах" button — regional+executive can edit branch goals
    can_edit_goals = can(user, "can_set_branch_goals")

    ctx = get_base_context(active_dashboard="branch")
    ctx.update({
        "dashboard_meta":   DASHBOARD_CATALOG.get("branch", {}),
        "scope_label":      get_scope_label(user),
        "show_back_button": len(get_dashboards(user)) > 1,
        "show_picker":      False,
        # data
        "summary":          summary,
        "goals":            goals,
        "workers":          workers,
        "activity":         activity,
        "can_edit_goals":   can_edit_goals,
        # for picker (regional/exec can switch branches)
        "visible_branches": scope_branches(Branch.query, user).order_by(Branch.name).all(),
        "current_branch_id": branch_id,
    })
    return render_template("dashboard/branch.html", **ctx)

def _build_bank():
    """Stub — Phase F (optional) will build this."""
    user = current_user()
    back = url_for("dashboard.menu") if len(get_dashboards(user)) > 1 \
           else url_for("auth.logout")
    return render_template_string(
        _STUB_TEMPLATE,
        icon="🏦",
        title="Банкны нэгтгэл",
        message="Энэ дашбоард удахгүй нэмэгдэнэ. (Phase F)",
        back_url=back,
    )
