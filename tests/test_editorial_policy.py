from __future__ import annotations

from src import editorial_policy


def test_describe_editorial_fit_scores_open_source_ai_stack() -> None:
    """Self-hosted AI tooling with GitHub cues should rank as a strong CIO-fit."""
    article = {
        "title": "GitHub release packages Docling, Qdrant, and Ollama into a self-hosted document AI stack",
        "text": (
            "The repo combines OCR, semantic search, and local models for contract review "
            "and policy lookup. Platform teams can deploy it with Docker and expose it to "
            "finance, sales, and construction staff as an internal copilot."
        ),
        "category_hint": "automation",
        "source_name": "GitHub",
        "url": "https://github.com/example/self-hosted-doc-ai",
    }

    fit = editorial_policy.describe_editorial_fit(article)

    assert fit["score"] >= 8
    assert "ai_knowledge_ops" in fit["track_ids"]
    assert "open_source_tooling" in fit["track_ids"]
    assert "it_platform" in fit["business_function_ids"]
    assert "knowledge_ops" in fit["business_function_ids"]


def test_describe_editorial_fit_stays_low_for_generic_corporate_update() -> None:
    """Generic company updates without a practical tool angle should stay off-radar."""
    article = {
        "title": "Vendor expands strategic partnership with regional developer",
        "text": (
            "The companies plan to collaborate on future digital transformation initiatives "
            "across several markets. Public technical detail and deployment specifics were not shared."
        ),
        "category_hint": "partnership",
        "source_name": "Corporate newsroom",
        "url": "https://example.com/partnership",
    }

    fit = editorial_policy.describe_editorial_fit(article)

    assert fit["score"] <= 2
    assert fit["track_ids"] == []


def test_describe_editorial_fit_scores_drone_site_intelligence() -> None:
    """Drone and computer-vision site-capture stories should match the site_intelligence track."""
    article = {
        "title": "Autonomous drone fleet completes RTK survey on active construction site",
        "text": (
            "The fleet uses computer vision and photogrammetry to track earthwork progress. "
            "Field crews receive daily orthomosaic updates without manual surveying."
        ),
        "category_hint": "robotics",
        "source_name": "DroneTech Weekly",
        "url": "https://example.com/drone-rtk",
    }

    fit = editorial_policy.describe_editorial_fit(article)

    assert "site_intelligence" in fit["track_ids"]
    assert "construction" in fit["business_function_ids"]
    assert fit["score"] >= 5


def test_describe_editorial_fit_scores_bim_digital_twin() -> None:
    """BIM interoperability and digital-twin workflows should match the bim_and_digital_twin track."""
    article = {
        "title": "Speckle connector federates IFC models into a live digital twin",
        "text": (
            "The new open-source connector streams IFC geometry and property sets into a "
            "Cesium-based twin. Clash detection runs automatically on every model commit."
        ),
        "category_hint": "bim",
        "source_name": "OpenBIM Blog",
        "url": "https://example.com/speckle-ifc",
    }

    fit = editorial_policy.describe_editorial_fit(article)

    assert "bim_and_digital_twin" in fit["track_ids"]
    assert "construction" in fit["business_function_ids"]
    assert fit["score"] >= 5


def test_describe_editorial_fit_scores_smart_building_ops() -> None:
    """Smart-building IoT and predictive-maintenance stories should match smart_building_ops."""
    article = {
        "title": "HVAC analytics platform cuts energy use by 18% across office portfolio",
        "text": (
            "Sensors on chillers and VAV boxes stream telemetry to a cloud-based fault-detection "
            "engine. Facility managers get predictive maintenance alerts two weeks ahead."
        ),
        "category_hint": "operations",
        "source_name": "FacilitiesTech",
        "url": "https://example.com/hvac-analytics",
    }

    fit = editorial_policy.describe_editorial_fit(article)

    assert "smart_building_ops" in fit["track_ids"]
    assert "operations" in fit["business_function_ids"]
    assert fit["score"] >= 5


def test_describe_editorial_fit_boosts_on_deployment_and_wow() -> None:
        """Stories with both deployment evidence and wow-factor keywords should score higher."""
        article = {
            "title": "Autonomous inspection robot deployed on three commercial sites",
            "text": (
                "The robot rolled out to active sites in Q1. It uses computer vision to detect "
                "rebar placement errors and runs self-hosted on a local edge server."
            ),
            "category_hint": "robotics",
            "source_name": "Construction Robotics",
            "url": "https://example.com/robot-deployed",
        }

        fit = editorial_policy.describe_editorial_fit(article)

        assert "site_intelligence" in fit["track_ids"]
        assert fit["deployment_hits"]
        assert fit["wow_hits"]
        assert fit["score"] >= 7


def test_describe_editorial_fit_moderate_score_for_single_track() -> None:
    """A single-track story without strong deployment or wow cues should have a moderate score."""
    article = {
        "title": "New lead routing module for CRM",
        "text": "Sales teams can now route incoming leads to the right rep automatically.",
        "category_hint": "sales",
        "source_name": "SalesTech",
        "url": "https://example.com/lead-routing",
    }

    fit = editorial_policy.describe_editorial_fit(article)

    assert fit["track_ids"] == ["sales_and_finance_automation"]
    assert fit["score"] >= 4
    assert fit["score"] <= 8
