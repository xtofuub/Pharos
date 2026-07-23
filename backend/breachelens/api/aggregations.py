"""Aggregation endpoints: services, domains, accounts."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from breachelens.state import AppState
from .auth import get_state, require_session

router = APIRouter(tags=["aggregations"], dependencies=[Depends(require_session)])


@router.get("/api/aggregations/services")
async def services(state: AppState = Depends(get_state)) -> list[dict]:
    rows = await state.db.fetchall(
        """
        SELECT COALESCE(service_name, 'Unknown') as svc,
               COUNT(*) as record_count,
               COUNT(DISTINCT account_hash) as unique_accounts,
               COUNT(DISTINCT source_id) as source_count
        FROM records
        GROUP BY svc
        ORDER BY record_count DESC
        """
    )
    out = []
    for r in rows:
        d = dict(r)
        # Get root domains for this service
        rd_rows = await state.db.fetchall(
            "SELECT DISTINCT root_domain FROM records WHERE COALESCE(service_name, 'Unknown') = ?",
            (d["svc"],),
        )
        out.append({
            "service_name": d["svc"],
            "root_domains": [row["root_domain"] for row in rd_rows if row["root_domain"]],
            "record_count": d["record_count"],
            "unique_account_count": d["unique_accounts"],
            "source_count": d["source_count"],
        })
    return out


@router.get("/api/aggregations/domains")
async def domains(state: AppState = Depends(get_state)) -> list[dict]:
    rows = await state.db.fetchall(
        """
        SELECT root_domain, COALESCE(service_name, 'Unknown') as service_name,
               COUNT(*) as record_count,
               COUNT(DISTINCT account_hash) as unique_accounts
        FROM records
        WHERE root_domain IS NOT NULL
        GROUP BY root_domain
        ORDER BY record_count DESC
        """
    )
    out = []
    for r in rows:
        d = dict(r)
        sub_rows = await state.db.fetchall(
            "SELECT DISTINCT subdomain FROM records WHERE root_domain = ? AND subdomain IS NOT NULL LIMIT 10",
            (d["root_domain"],),
        )
        out.append({
            "root_domain": d["root_domain"],
            "service_name": d["service_name"],
            "record_count": d["record_count"],
            "unique_account_count": d["unique_accounts"],
            "top_subdomains": [row["subdomain"] for row in sub_rows],
        })
    return out


@router.get("/api/aggregations/accounts")
async def accounts(state: AppState = Depends(get_state)) -> list[dict]:
    rows = await state.db.fetchall(
        """
        SELECT MIN(COALESCE(email, username)) as masked_account,
               COUNT(DISTINCT service_name) as service_count,
               COUNT(DISTINCT root_domain) as domain_count,
               COUNT(DISTINCT source_id) as source_count,
               MIN(created_at) as first_seen,
               MAX(created_at) as last_seen
        FROM records
        WHERE account_hash IS NOT NULL
        GROUP BY account_hash
        ORDER BY source_count DESC
        LIMIT 100
        """
    )
    out = []
    for r in rows:
        d = dict(r)
        # Mask the account
        from breachelens.security.masking import mask_email, mask_value
        account = d["masked_account"]
        if account and "@" in account:
            masked = mask_email(account)
        elif account:
            masked = mask_value(account, 2)
        else:
            masked = "••••"
        out.append({
            "masked_account": masked,
            "service_count": d["service_count"],
            "domain_count": d["domain_count"],
            "source_count": d["source_count"],
            "first_seen": d["first_seen"],
            "last_seen": d["last_seen"],
        })
    return out
