import unittest
from unittest.mock import patch

from agent_store import AgentStore
from company_api import build_company_router
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient


class TalentMarketTests(unittest.TestCase):
    def setUp(self):
        self.store = AgentStore()
        self.mock = patch("company_api.get_agent_store", return_value=self.store)
        self.mock.start()
        self.addCleanup(self.mock.stop)

        def actor(x_actor: str = Header()):
            return x_actor

        app = FastAPI()
        app.include_router(build_company_router(actor))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.profile = dict(
            name="  Alex  ",
            role="Product designer",
            summary="I design clear and thoughtful digital products for small teams.",
            skills=[" UI design ", "Flutter", "UI design"],
            availability="available",
            rate=35,
            pricing="hour",
            published=True,
        )

    def put(self, actor="alex", **changes):
        return self.client.put(
            "/company/talent/profile",
            headers={"X-Actor": actor},
            json=dict(self.profile, **changes),
        )

    def test_self_publish_is_public_but_only_owner_can_edit_or_remove(self):
        profile = self.put().json()
        self.assertEqual(profile["name"], "Alex")
        self.assertEqual(profile["skills"], ["UI design", "Flutter"])
        public = self.client.get(
            "/company/talent", headers={"X-Actor": "founder"}
        ).json()["profiles"]
        self.assertEqual(public[0]["id"], profile["id"])
        self.assertFalse(public[0]["is_mine"])
        self.assertNotIn("actor_id", public[0])
        self.client.delete("/company/talent/profile", headers={"X-Actor": "founder"})
        self.assertIsNotNone(self.store.get_talent_profile("alex"))
        updated = self.put(
            summary="Updated summary about creating excellent product experiences."
        ).json()
        self.assertEqual(updated["id"], profile["id"])
        self.put(published=False)
        self.assertEqual(self.store.list_talent_profiles("founder"), [])
        self.assertIsNotNone(self.store.get_talent_profile("alex"))
        self.client.delete("/company/talent/profile", headers={"X-Actor": "alex"})
        self.assertIsNone(self.store.get_talent_profile("alex"))

    def test_rate_bio_and_skills_validation(self):
        for bad in [
            dict(rate=-1),
            dict(rate=100001),
            dict(name="   "),
            dict(summary="too short"),
            dict(skills=["a" * 41]),
            dict(availability="always"),
        ]:
            with self.subTest(bad=bad):
                self.assertEqual(self.put(**bad).status_code, 422)
        self.assertEqual(self.put(pricing="volunteer", rate=99).json()["rate"], 0)

    def test_brief_is_private_draft_and_cannot_target_withdrawn_or_unavailable_profile(
        self,
    ):
        profile = self.put().json()
        path = f"/company/talent/{profile['id']}/briefs"
        brief = dict(session_id="project-a", description="Design our homepage")
        response = self.client.post(path, headers={"X-Actor": "founder"}, json=brief)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "draft_assignment")
        self.assertEqual(len(self.store.list_human_tasks("founder", "project-a")), 1)
        self.assertEqual(self.store.list_human_tasks("alex", "project-a"), [])
        self.put(availability="unavailable")
        self.assertEqual(
            self.client.post(
                path, headers={"X-Actor": "founder"}, json=brief
            ).status_code,
            404,
        )
        self.put(published=False)
        self.assertEqual(
            self.client.post(
                path, headers={"X-Actor": "founder"}, json=brief
            ).status_code,
            404,
        )

    def test_employee_addition_is_private_and_project_scoped(self):
        employee = dict(
            name="My employee",
            role="Research assistant",
            summary="Helps our internal team organize research and evidence.",
            skills=["Research", "Writing"],
            department="research",
            session_id="project-a",
            rate=25,
            pricing="hour",
            availability="available",
        )
        response = self.client.post(
            "/company/humans", headers={"X-Actor": "founder"}, json=employee
        )
        self.assertEqual(response.status_code, 201)
        person = response.json()
        self.assertEqual(person["department"], "research")
        self.assertEqual(person["skills"], ["Research", "Writing"])
        public = self.client.get(
            "/company/talent", headers={"X-Actor": "stranger"}
        ).json()["profiles"]
        self.assertEqual(len(public), 1)
        self.assertTrue(public[0]["is_example"])
        self.assertEqual(
            self.client.get(
                "/company/humans?session_id=project-a", headers={"X-Actor": "stranger"}
            ).json()["employees"],
            [],
        )
        self.assertEqual(
            self.client.get(
                "/company/humans?session_id=project-b", headers={"X-Actor": "founder"}
            ).json()["employees"],
            [],
        )
        own = self.client.get(
            "/company/humans?session_id=project-a", headers={"X-Actor": "founder"}
        ).json()["employees"]
        self.assertEqual(own[0]["id"], person["id"])
        bad = self.client.post(
            "/company/human-tasks",
            headers={"X-Actor": "stranger"},
            json={
                "employee_id": person["id"],
                "session_id": "project-a",
                "description": "Review our research",
            },
        )
        self.assertEqual(bad.status_code, 404)

    def test_example_is_visible_but_never_hired_or_owned(self):
        profiles = self.client.get(
            "/company/talent", headers={"X-Actor": "founder"}
        ).json()["profiles"]
        self.assertEqual(len(profiles), 1)
        example = profiles[0]
        self.assertTrue(example["is_example"])
        self.assertFalse(example["is_mine"])
        self.assertEqual(example["availability"], "unavailable")
        self.assertIsNone(self.store.get_talent_profile("founder"))
        response = self.client.post(
            "/company/talent/" + example["id"] + "/briefs",
            headers={"X-Actor": "founder"},
            json={"session_id": "project-a", "description": "Do real work"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.store.list_human_tasks("founder", "project-a"), [])


if __name__ == "__main__":
    unittest.main()
