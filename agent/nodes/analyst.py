"""
Job Analyst - turns a messy job post into a structured JobSpec.

Model: small (gpt-oss-20b). No tools: it only reads the job text.
Safety: the post is wrapped as untrusted data and injection sentences are removed
before the model sees them; regex also lists them in `suspicious_instructions`.
"""

from agent import llm
from agent.handoffs import JobExtract, JobSpec
from agent.nodes.base import node
from agent.safety import find_injections, wrap_untrusted


@node("job_analyst")
async def job_analyst(state, config):
    job = state["job"]
    extract, usage = await llm.structured(
        "job_analyst", "job_analyst", JobExtract,
        title=job["title"], skills=", ".join(job["required_skills"]),
        job_block=wrap_untrusted("job_post", job["description"]))
    spec = JobSpec(**extract.model_dump(), job_id=job["job_id"], title=job["title"], category=job["category"],
                   budget_min=job["budget"]["min"], budget_max=job["budget"]["max"],
                   screening_questions=job["screening_questions"])
    # Facts from the marketplace beat the model; injections found by regex are always listed.
    spec.suspicious_instructions = list(dict.fromkeys(spec.suspicious_instructions + find_injections(job["description"])))
    if not spec.requirements:
        spec.requirements = list(job["required_skills"])
    return {"job_spec": spec.model_dump(), "usage": [usage]}
