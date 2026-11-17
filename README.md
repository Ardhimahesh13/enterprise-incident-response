
# Enterprise Incident Co-Pilot: Self-RAG & Corrective-RAG Enterprise Incident Response Copilot

An autonomous AI Site Reliability Engineering (SRE) assistant built with **LangGraph**, **LangChain**, **FastAPI**, **Groq**, and **Pinecone** that investigates production incidents, retrieves internal runbooks, falls back to real-time web search when internal knowledge is insufficient, and evaluates generated responses to minimize hallucinations before delivering troubleshooting recommendations to engineers.

---

## Core Capabilities

### 1. Corrective-RAG (CRAG) Routing

Unlike traditional RAG pipelines that blindly pass retrieved documents to an LLM, Enterpirse Incident Co-Pilot evaluates the relevance of retrieved runbook chunks before generating a response.

- **Document Relevance Grading:** Evaluates retrieved runbook chunks to determine whether they contain relevant information for the incident.
- **Query Rewriting:** Automatically rewrites the original query when retrieved documentation lacks sufficient context.
- **Web Search Fallback:** Integrates the **Tavily Search API** to retrieve external information when internal documentation does not provide adequate coverage.
- **Adaptive Retrieval:** Dynamically determines whether to continue with internal knowledge retrieval or switch to external search.

### 2. Self-RAG Hallucination Guardrails

Implements two strict LLM-as-a-Judge evaluation gates to validate generated troubleshooting recommendations before delivering them to engineers.

- **Support Evaluation (IsSUP):** Checks whether the identified root cause and recommended CLI commands are supported by retrieved evidence.
- **Usefulness Evaluation (IsUSE):** Evaluates whether the generated response contains relevant, practical, and actionable incident resolution steps.
- **Evidence-Based Generation:** Minimizes unsupported root-cause explanations and hallucinated troubleshooting commands.

### 3. Persistent Multi-Turn Incident Threads

Implements stateful incident conversations using **LangGraph Checkpointing** and SQLite.

- Uses `langgraph-checkpoint-sqlite` to persist conversation states.
- Maintains separate investigation sessions using unique Thread IDs.
- Supports multi-turn incident investigations across incidents such as `INC-001` and `INC-004`.
- Allows engineers to continue previous investigations without losing conversational context.

### 4. Real-Time Workflow Observability

Provides visibility into the internal execution of the agentic workflow through an interactive frontend dashboard.

- Displays step-by-step LangGraph node execution.
- Tracks document retrieval and retention counts.
- Displays Self-RAG evaluation results (`IsSUP` and `IsUSE`).
- Provides real-time workflow execution visibility.
- Helps engineers understand how the AI system retrieves, evaluates, and generates incident resolution recommendations.

### 5. Automated CI/CD and AWS Deployment

Implements an automated deployment pipeline using **Docker**, **GitHub Actions**, and **AWS EC2**.

- Containerizes the application using Docker.
- Uses CPU-only PyTorch (`torch==2.6.0+cpu`) to reduce unnecessary GPU-related dependencies.
- Automates deployment through GitHub Actions whenever changes are pushed to the `main` branch.
- Transfers application artifacts to AWS EC2 using SSH and SCP.
- Injects production API credentials securely through GitHub Secrets.
- Deploys the application on Ubuntu 24.04 LTS.
- Uses Docker restart policies to maintain application availability.

---

## Technology Stack

| Layer | Technologies |
|---|---|
| Agent Orchestration | LangGraph, LangChain |
| RAG Architecture | Self-RAG, Corrective-RAG (CRAG) |
| LLM Provider | Groq API |
| Embedding Model | HuggingFace Sentence Transformers (`all-MiniLM-L6-v2`) |
| Vector Database | Pinecone |
| External Search | Tavily Search API |
| Backend | FastAPI, Uvicorn |
| Conversation Persistence | SQLite, `langgraph-checkpoint-sqlite` |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Containerization | Docker |
| CI/CD | GitHub Actions |
| Cloud Infrastructure | AWS EC2 |
| Operating System | Ubuntu 24.04 LTS |

---

## Architecture & Agentic Workflow

Enterpirse Incident Co-Pilot follows a graph-based agentic architecture using LangGraph.

Instead of relying on a single retrieval-and-generation step, the workflow incorporates document relevance grading, adaptive retrieval, query rewriting, external web search, response generation, and hallucination evaluation.

### High-Level Workflow

```text
                User Incident Query
                        |
                        v
                 Query Processing
                        |
                        v
                Retrieve Runbooks
                        |
                        v
               Document Grading
                        |
                 +------+------+
                 |             |
                 v             v
          Relevant Docs    Irrelevant Docs
                 |             |
                 v             v
          Generate Answer  Rewrite Query
                 |             |
                 |             v
                 |       Tavily Web Search
                 |             |
                 |             v
                 |       Generate Answer
                 |             |
                 +------+------+
                        |
                        v
                 Self-RAG Evaluation
                        |
                 +------+------+
                 |             |
                 v             v
            IsSUP Check    IsUSE Check
                 |             |
                 +------+------+
                        |
                        v
              Validated Response
                        |
                        v
                 Engineer UI
```

---

## Project Structure

```text
enterprise-incident-response/
│
├── .github/
│   └── workflows/
│       └── deploy.yml          # Automated CI/CD pipeline to AWS EC2
│
├── app/
│   ├── main.py                 # FastAPI endpoints and static UI serving
│   ├── graph.py                # LangGraph state machine (CRAG + Self-RAG)
│   └── ...                     # Vector store, grader prompts and state schemas
│
├── ui/                         # Frontend dashboard
│   └── ...                     # AI Copilot, Workflow Monitor, Knowledge Base
│
├── Dockerfile                  # Python 3.12 + CPU-only PyTorch image
├── .dockerignore               # Excludes secrets, virtual environments and local files
└── requirements.txt            # Python dependencies
```

---

## Local Setup & Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Ardhimahesh13/enterprise-incident-response.git

cd enterprise-incident-response
```

### 2. Create a Virtual Environment

**Windows:**

```powershell
python -m venv venv

venv\Scripts\activate
```

**Linux / macOS:**

```bash
python -m venv venv

source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project's root directory.

```env
GROQ_API_KEY=your_groq_api_key

PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=runbooks

TAVILY_API_KEY=your_tavily_api_key

EMBEDDING_MODEL=all-MiniLM-L6-v2
```

**Important:** Replace the placeholder values with your actual API credentials. Never commit your `.env` file or expose API keys in your GitHub repository.

### 5. Start the Application

```bash
uvicorn app.main:app --reload --port 8000
```

### 6. Access the Application

Open your browser:

```text
http://localhost:8000
```

---

## Production Deployment: Docker + GitHub Actions + AWS EC2

Enterpirse Incident Co-Pilot uses an automated CI/CD pipeline to deploy application updates to AWS EC2.

Every push to the `main` branch triggers the GitHub Actions workflow defined in:

```text
.github/workflows/deploy.yml
```

### Deployment Pipeline

1. **GitHub Actions Trigger:** Automatically starts the deployment workflow when changes are pushed to the `main` branch.

2. **Artifact Transfer:** Transfers application files to AWS EC2 using SSH and SCP while excluding unnecessary files such as `.git`, local secrets, and virtual environments.

3. **Environment Configuration:** Retrieves production API credentials from GitHub Secrets and configures the server-side `.env` file.

4. **Docker Image Build:** Builds a lightweight Docker image using Python 3.12 and CPU-only PyTorch dependencies.

5. **Resource Optimization:** Uses CPU-only PyTorch wheels through the following package index:

   ```bash
   --extra-index-url https://download.pytorch.org/whl/cpu
   ```

6. **Container Deployment:** Replaces the existing application container with the newly built container.

7. **Automatic Restart:** Configures Docker with `--restart unless-stopped` to automatically restart the application container when required.

8. **Port Mapping:** Exposes the application through port 80.

### Deployment Architecture

```text
Developer
    |
    v
GitHub Repository
    |
    v
GitHub Actions
    |
    v
CI/CD Pipeline
    |
    +------ SCP / SSH
    |
    v
AWS EC2 (Ubuntu 24.04)
    |
    v
Docker Image Build
    |
    v
Docker Container
    |
    v
FastAPI Backend
    |
    v
AegisOps Incident Response Copilot
```

---

## Key Engineering Highlights

- Designed an agentic incident investigation system using LangGraph.
- Implemented Corrective-RAG (CRAG) for adaptive document retrieval and query rewriting.
- Integrated Tavily Web Search as an external knowledge fallback.
- Developed Self-RAG evaluation mechanisms using dual LLM-as-a-Judge gates (`IsSUP` and `IsUSE`).
- Integrated Pinecone for semantic retrieval of enterprise incident runbooks.
- Implemented persistent multi-turn conversations using SQLite checkpointing.
- Built an interactive frontend dashboard for workflow execution monitoring and evaluation visibility.
- Containerized the application using Docker with CPU-only PyTorch dependencies.
- Automated production deployment using GitHub Actions and AWS EC2.

---

## Future Enhancements

- Advanced incident classification and prioritization.
- Improved retrieval evaluation and relevance scoring.
- Enhanced root-cause analysis capabilities.
- Integration with enterprise monitoring platforms.
- Advanced workflow performance metrics and observability.
- Automated incident resolution recommendations.

---

## Author


**Ardhi Mahesh**

- GitHub: [@Ardhimahesh13](https://github.com/Ardhimahesh13)

---
---

## Live Deployment

* **Live Application:** [EnterpriseAI Incident Copilot (AWS EC2)](http://32.198.2.0/)
* **API Health / Docs:** [FastAPI Swagger UI](http://32.198.2.0/docs)

> **Note:** Hosted on an AWS EC2 instance (`Ubuntu 24.04` + Docker). If the instance is temporarily paused between demos to conserve cloud credits, follow the local setup steps below or reach out for a live walkthrough.
## License

This project is developed for educational, research, and engineering purposes.


