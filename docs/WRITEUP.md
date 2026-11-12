# Every retrieval trick I added made my agent worse

For a course project I built GigBid, a set of AI agents that helps a freelancer bid on jobs. It
reads new job posts, flags scams, checks each requirement against the freelancer's portfolio,
prices the bid and drafts a proposal. A human approves every proposal before it goes out.

One rule shaped the design: the proposal may only claim what the portfolio can prove. If a client
asks for Celery and the freelancer has never shipped Celery, the proposal must not say otherwise.
That puts retrieval at the centre of the system. Before the Writer agent drafts anything, a
retriever has to find the case study, repository or client review that proves each skill.

I followed the usual RAG advice and made retrieval smarter one layer at a time. When I measured
it, each layer made it worse.

## The prediction I wrote down first

Before running anything I committed a file of hypotheses to the repository, so that I could not
quietly adjust my expectations after seeing the results. The main one read:

> Requirement decomposition plus hybrid BM25 and dense retrieval raises evidence Recall@5 by at
> least 15 points over naive dense retrieval.

I believed it. A job post mixes several asks ("FastAPI service, background jobs, handle 100k
texts, Docker"), and one embedding of the whole post seemed likely to blur them together. One query
per requirement should keep each ask sharp. Exact tool names like "Celery" or "dbt" are what
keyword search (BM25) handles well and what a small embedding model might lose.

I also predicted that the gain would be largest on short, vague job posts, and that a cross-encoder
reranker would add a little on top.

## The setup

I hand-marked the correct evidence for 36 job posts across three freelancer personas: an ML
engineer, a web developer and a data analyst. Each persona has a small portfolio of case studies,
repositories, client reviews and a CV, cut into 40-word chunks. I compared five retrievers:

- V0 embeds the whole job post and returns the nearest chunks.
- V1 has an LLM split the post into requirements and runs one search per requirement.
- V2 adds BM25 keyword search to V1, merged with reciprocal rank fusion.
- V3 adds a cross-encoder reranker to V2.
- V8 adds a corrective loop to V3. If the best evidence scores too low, it rewrites the query, and
  if the evidence is still weak, it returns nothing.

All the models were small, open and running on a CPU. The number I cared about most was Recall@5:
of the evidence that proves a job's requirements, how much appears in the top five results.

## What happened

| Retriever | Recall@5 | MRR | p95 latency |
|---|---|---|---|
| V0, naive dense | 0.898 | 1.00 | 18 ms |
| V1, decomposition | 0.803 | 0.86 | 40 ms |
| V2, + hybrid | 0.836 | 0.92 | 44 ms |
| V3, + reranker | 0.810 | 0.79 | 1,268 ms |
| V8, + corrective loop | 0.854 | 0.88 | 1,678 ms |

The simplest retriever won on every measure. My hypothesis pointed the wrong way: decomposition
plus hybrid search lost about 6 points, and with the embedding model I started with it lost 15. I
was wrong about vague posts too. Decomposition did worst on them, 0.733 against 0.900 for the naive
version. The reranker lowered both recall and MRR and made each search about seventy times slower.

## Finding the step that caused it

A result like this hides a lot. Hybrid search might have been fine and the reranker at fault, or
every stage might have been a little bad. To find out, I took the full V8 pipeline and removed one
component at a time:

- Without decomposition, Recall@5 rose to 0.944, the best score in the whole study.
- Without hybrid search it stayed at 0.854.
- Without the reranker it fell to 0.836.
- Without the corrective loop it fell to 0.810.

Decomposition caused nearly all of the damage. With it removed, the advanced pipeline beat
everything else. BM25 made no difference either way, and the corrective loop added about four
points.

The failures explained it. When an LLM splits a vague post into requirements, the pieces are tiny:
"Python", "machine learning", "API". A one-word query matches every chunk that mentions Python,
which in a developer's portfolio is nearly all of them. The whole post carries context about what
the client is building and why, so its embedding finds the case study that matches the situation
instead of the keyword.

The portfolios are also small, about a dozen items each. Most retrieval advice comes from search
over millions of web pages, where recall is hard and a reranker pays for itself. With a dozen items,
plain similarity search already finds most of the right ones, and each extra stage mostly adds
another chance to push the right item down. My reranker was trained on web search queries. I think
it rewards chunks that repeat the query's words, while the chunk that proves a skill often describes
it in other words. I have not tested that explanation directly.

## Better retrieval did not bring more replies

The project includes a simulated marketplace whose client agents read proposals and decide whether
to reply. That let me check the number a freelancer cares about, the reply rate.

Retrieval quality and replies did not move together. The ML engineer persona had the best
retrieval of the three (Recall@5 0.958) and the most invented claims in the Writer's raw drafts,
and its reply rate matched the web developer's, whose retrieval was much weaker. The data analyst
had middling retrieval and the lowest reply rate.

The clearest case came from another experiment, where I compared my hand-built agent graph with a
prebuilt supervisor architecture. The supervisor's proposals carried 1.29 unsupported claims each
and got replies 86% of the time. My graph sends no unsupported claims and got 67%. The supervisor
sent only seven proposals, so the gap is not statistically meaningful, but it worried me anyway.

The simulated clients like a specific opening and concrete numbers, and they never check a claim
against the portfolio. Real clients mostly don't either, until the work starts. Grounding protects
the freelancer's reputation and the client's money, and a reply rate cannot see either. Had I tuned
the system on reply rate alone, the tuning would have pushed it toward invented claims.

## Where the complicated version paid off

The corrective loop lost to plain search at finding evidence, but it could do one thing nothing
else did: decide that there is no evidence. For requirements the freelancer cannot meet, it
returned nothing 100% of the time, and it wrongly refused only 2% of real skills.

Another agent needs exactly that. The Fit Matcher decides whether a job is worth bidding on, and
for that decision an honest "no evidence" is worth more than a plausible wrong match. GigBid ships
both: the simplest retriever supplies the Writer's evidence, and the corrective pipeline drives the
fit decision.

## Measuring the cheaper model

Near the end I deployed on a free host with 512 MB of memory, and my first embedding model did not
fit. A smaller one did. I re-ran the whole evaluation before switching: Recall@5 dropped from 0.947
to 0.898, and every conclusion above still held. Five points is a real cost. Because I measured it,
it is written into the design record, and nobody has to discover it later as a mystery regression.

## What I would tell myself at the start

Write the prediction down before the experiment. Mine was confidently wrong, and the commit history
shows I did not edit it afterwards.

Ablate a pipeline before trusting or rejecting it. The advanced pipeline was one bad step away from
being the best, and without the ablation I would have blamed the reranker or thrown out the whole
thing.

Consider the size of the corpus. Techniques designed for millions of documents can hurt on a dozen.

Measure the outcome as well as the component. Retrieval scores, reply rates and truthfulness pulled
in different directions here, and I had to decide which one I was willing to give up before the
numbers made that choice for me.

Let each part of the system use the method that fits its task. The retriever that lost for one
agent was the right one for another.

I set out to build a better retriever. What the experiments gave me was evidence that the simple
one was good enough for writing proposals, and a clear view of the one place where the complex one
earns its cost.
