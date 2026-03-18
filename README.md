# 🌱 Mars Agriculture Hackathon — Getting Started Guide

Welcome, hackers! Your mission is to design and prototype an autonomous AI agent system capable of managing a greenhouse on Mars... You'll use AWS cloud services, an AI-powered Knowledge Base (via MCP) to get crop data, and Kiro as your AI coding assistant.

> 💡 **Tip:** AWS Amplify Gen2 is an easy way to get a frontend deployed quickly. If you need other AWS services that Amplify supports (Authentication, Data/GraphQL API, Storage, Functions), feel free to use those too. For anything else, you can use the AWS SDK, CDK, or Console directly — it's up to your team.

---

## 📦 What You've Been Given

| Resource | Scope |
|---|---|
| AWS Sandbox Account (via Workshop Studio) | 1 per team |
| Kiro Access Code | 1 per person |

---

## 🛠️ Prerequisites — Install These First

### 1. Node.js (v18 or later)

- Download from [https://nodejs.org](https://nodejs.org) (use the LTS version)
- Verify installation:
  ```bash
  node --version
  npm --version
  ```

### 2. Git

- Download from [https://git-scm.com](https://git-scm.com)
- Verify:
  ```bash
  git --version
  ```

### 3. AWS CLI

- **macOS:** `brew install awscli` (or download from [AWS CLI Install](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html))
- **Windows:** Download the MSI installer from the link above
- **Linux:** `curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && unzip awscliv2.zip && sudo ./aws/install`
- Verify:
  ```bash
  aws --version
  ```

### 4. Kiro IDE 

- Download from [https://kiro.dev/downloads](https://kiro.dev/downloads)
- Choose the installer for your operating system (macOS / Windows / Linux)
- Install and launch Kiro

---

## 🔐 Step 1 — Get Your AWS Credentials from Workshop Studio

Each team has **one shared AWS sandbox account** provisioned through AWS Workshop Studio.

### Access Workshop Studio

1. Go to the Workshop Studio URL provided by the organizers
2. Sign in with the credentials or event code given to your team
3. Once logged in, click **"Open AWS Console"** to access your sandbox account

### Get CLI Credentials

To use AWS from your terminal (needed for Amplify and for the AWS CLI), you need to copy the temporary credentials:

1. In Workshop Studio, look for the **"Get AWS CLI credentials"** section (or click on your account details)
2. You'll see three values: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN`
3. Copy the **export commands** (Option 1 for macOS/Linux, Option 2 for Windows) and paste them into your terminal:

**macOS / Linux:**
```bash
export AWS_ACCESS_KEY_ID="<value-from-workshop-studio>"
export AWS_SECRET_ACCESS_KEY="<value-from-workshop-studio>"
export AWS_SESSION_TOKEN="<value-from-workshop-studio>"
export AWS_DEFAULT_REGION="us-east-1"
```

**Windows (PowerShell):**
```powershell
$env:AWS_ACCESS_KEY_ID="<value-from-workshop-studio>"
$env:AWS_SECRET_ACCESS_KEY="<value-from-workshop-studio>"
$env:AWS_SESSION_TOKEN="<value-from-workshop-studio>"
$env:AWS_DEFAULT_REGION="us-east-1"
```

> ⚠️ **These credentials are temporary and will expire.** If you get authentication errors later, go back to Workshop Studio and copy fresh credentials.

Verify it works:
```bash
aws sts get-caller-identity
```

You should see your account ID in the output.

---

## 🤖 Step 2 — Set Up Kiro IDE

Kiro is an AI-powered IDE that can write code, run commands, read files, and help you build your app.

### Authenticate

1. Launch Kiro IDE
2. When prompted, sign in and enter your personal Kiro access code, this code has been provided to you in the team envelop

### Open your project

Once you've created your project (see Step 3), open the project folder in Kiro via **File → Open Folder**.

### Review the Steering Files

This repository includes Kiro **steering files** in the `.kiro/steering/` folder. These files guide Kiro's behavior when generating code for your project.

- **`tech.md`** — Defines the recommended tech stack for the hackathon. Kiro will follow these directives when writing code.
- You're free to **modify or replace** the tech stack in `tech.md` if your team prefers different technologies.
- Take a moment to **review all the steering files** in `.kiro/steering/` to make sure you're comfortable with the directives. Edit them to match your team's preferences if needed.

> 💡 Steering files are how you tell Kiro *how* you want your code written — think of them as project-level instructions for your AI teammate.

### Enable Strands SDK and Amplify Powers

Kiro has built-in "Powers" that give the AI deeper knowledge of specific frameworks. Enable these two for the hackathon:

1. Open the **Powers** panel in Kiro (click the Powers icon in the sidebar or use the Command Palette: `Ctrl+Shift+P` / `Cmd+Shift+P` → search "Powers")
2. Enable **Strands SDK** — gives Kiro knowledge of the Strands Agents SDK for building AI agents
2. Enable **Amplify** — gives Kiro knowledge of AWS Amplify Gen2 patterns, schema syntax, and best practices

> ⚠️ Make sure both powers show as **enabled** before you start prompting Kiro. This significantly improves the quality of generated code for Amplify and Strands.

### Useful Kiro features

| Feature | How |
|---|---|
| AI Chat | Use the built-in chat panel to ask questions, generate code, and debug |
| Code Intelligence | Kiro provides autocomplete, go-to-definition, and diagnostics out of the box |
| Terminal | Use the integrated terminal (`Ctrl+`` / `Cmd+``) to run commands |
| Planner | Use `Shift + Tab` in the chat to break down tasks into steps |

> 💡 **Tip:** You can ask Kiro to write code, explain AWS concepts, debug errors, and even run terminal commands for you. Treat it as your AI teammate!

---

## 🚀 Step 3 — Create Your Project

### You can follow the manual instructions here below, or skip to the suggested Kiro prompts session and ask Kiro to set it up for you!

AWS Amplify Gen2 is an easy way to get a React frontend deployed quickly. If Amplify supports other services you need (auth, data, storage, functions), you can use those too. Otherwise, provision backend resources however your team prefers — AWS Console, CDK, SDK, etc.

### Create a new Amplify project

```bash
npm create amplify@latest mars-tomato-app
cd mars-tomato-app
```

Follow the prompts (defaults are fine).

### Install dependencies

```bash
npm install
```

### Understand the project structure

```
mars-tomato-app/
├── amplify/           # ← Backend definitions (if using Amplify for backend services)
│   ├── auth/          #   Authentication setup
│   ├── data/          #   Database / API schema
│   └── backend.ts     #   Backend entry point
├── src/               # ← Your frontend lives here (React)
├── package.json
└── ...
```

### Start the dev environment

```bash
npm run dev
```

If you're using Amplify for backend services, run the sandbox in a separate terminal:
```bash
npx ampx sandbox
```

---

## 🌱 Step 4 — Connect to the Mars Crop Knowledge Base (MCP)

The organizers provide an **MCP server** that gives you access to a knowledge base about Martian greenhouse agriculture — crop profiles, environmental constraints, nutrient management, operational scenarios, and more.

**MCP Endpoint URL:**
```
https://kb-start-hack-gateway-buyjtibfpg.gateway.bedrock-agentcore.us-east-2.amazonaws.com/mcp
```

### Configure the MCP server using Kiro

The easiest way to set this up is to ask Kiro to do it for you. In Kiro's chat, try:

> *"Configure an MCP server using streamable HTTP at this URL: https://kb-start-hack-gateway-buyjtibfpg.gateway.bedrock-agentcore.us-east-2.amazonaws.com/mcp"*

Kiro will create the `.kiro/settings/mcp.json` file for you. If you prefer to do it manually, create that file with:

```json
{
  "mcpServers": {
    "mars-crop-knowledge-base": {
      "type": "streamableHttp",
      "url": "https://kb-start-hack-gateway-buyjtibfpg.gateway.bedrock-agentcore.us-east-2.amazonaws.com/mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

After configuring, reload Kiro (`Cmd+Shift+P` / `Ctrl+Shift+P` → `Developer: Reload Window`).

### Using the Knowledge Base

Once the MCP server is connected, you can ask Kiro to query it. Here are some examples:

- *"What are the optimal temperature and humidity ranges for growing lettuce on Mars?"*
- *"Query the knowledge base for water requirements per crop growth stage"*
- *"What crops are best suited for a 450-day Mars mission and why?"*
- *"What happens if the water recycling system fails in the greenhouse? What should the AI do?"*
- *"Use the knowledge base to build a data model for tracking crop health in my app"*

Kiro will automatically call the MCP tool, retrieve relevant data from the knowledge base, and use it in its responses or code generation.

---

## 🤖 Step 5 — Deploy Your Agentic Application on Amazon Bedrock AgentCore

If you're building an AI agent (e.g., an autonomous greenhouse manager), consider deploying it on **Amazon Bedrock AgentCore**. AgentCore provides infrastructure for hosting, scaling, and operating AI agents with built-in support for tool use, memory, and orchestration.

> 💡 **Tip:** Ask Kiro to help you set up an AgentCore deployment. Enable the **AgentCore Power** in Kiro's Powers panel for framework-aware code generation.

### Reference Repositories

These repos contain working examples you can use as a starting point:

- [Amazon Bedrock AgentCore Samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples) — Sample agents and patterns for AgentCore
- [Full-Stack Solution Template for AgentCore](https://github.com/awslabs/fullstack-solution-template-for-agentcore) — End-to-end template with frontend and AgentCore backend

---

## 🧬 Step 6 — Build AI Agents with Strands SDK (Optional)

If you want to build AI agents for your application (e.g., a crop advisor, an autonomous greenhouse controller), the **Strands Agents SDK** is a good option. It's an open-source Python SDK for building agents that can use tools, call LLMs, and orchestrate multi-step reasoning.

You're not required to use it — any agent framework works — but Strands integrates well with AWS Bedrock models and Kiro has built-in support for it via the **Strands SDK Power**.

### Getting Started with Strands

```bash
pip install strands-agents strands-agents-tools
```

> 💡 **Tip:** Enable the **Strands SDK Power** in Kiro's Powers panel, then ask Kiro to help you build an agent. For example:
>
> *"Create a Strands agent that queries the Mars crop knowledge base and recommends optimal growing conditions"*
>
> *"Build a multi-tool agent with Strands that monitors sensor data and adjusts greenhouse parameters"*

---

## 💬 Suggested Kiro Prompts — Building Your Architecture

Not sure how to set up the technical pieces? Use these prompts in Kiro's chat to scaffold your AWS infrastructure. Copy-paste them or adapt them to your needs!

### 🗄️ Database & Data Modeling

> *"Create a DynamoDB table using AWS CDK with the following keys: [list of keys and value type]"*

> *"Write a utility module that uses the AWS SDK to read and write to my DynamoDB table."*

### �️ Database & Data Modeling

> *"Define a DynamoDB table with the following keys: [list of keys and value type]"*

> *"Write a utility module that reads and writes to my DynamoDB table."*

### �🔐 Authentication & Authorization

> *"Set up Cognito Auth with email-based sign-up and login in my project."*

### ⚡ Serverless Functions (Lambda)

> *"Create a Lambda function that [the purpose of your function goes here]."*

> *"Add a scheduled Lambda function that runs every 15 minutes."*

> *"Fix the error in my Lambda function. You can query the CloudWatch logs to find out about the error."*

### 🌐 API Layer

> *"Generate a REST API endpoint that triggers a Lambda function."*

### 📁 Storage (S3)

> *"Add an S3 bucket called [your name], add some random string to the name such that I'm sure the name is unique."*

> *"Create a React component that uploads files to my S3 bucket and lists the uploaded files."*

### 🔄 Real-Time & Subscriptions

> *"Enable real-time subscriptions so the frontend updates automatically when data changes."*

### 🐛 Debugging & Help

> *"I'm getting this error when running my AWS CDK deployment: [paste error]. Fix it."*


> 💡 **Pro tip:** After each prompt, review what Kiro generates, test it, and then build on top of it with the next prompt. Iterating in small steps is the fastest way to make progress!

---

## 🧪 Quick Sanity Check
> *"I'm getting this error: [paste error]. Fix it."*
By this point you should have:

- [x] AWS credentials from Workshop Studio configured and `aws sts get-caller-identity` works
- [x] Kiro IDE installed, authenticated, and project opened
- [x] Amplify frontend project created and `npm run dev` running
- [x] Backend services provisioned via AWS Console or CDK
- [x] MCP server configured for the Mars Crop Knowledge Base

---

## 💡 Tips for Success

- [x] Project created and `npm run dev` runningt to break down your idea into steps before coding.
3. **Start simple.** Get a basic CRUD app working first, then add features.
4. **Check the Amplify docs for frontend/hosting.** [https://docs.amplify.aws/gen2/](https://docs.amplify.aws/gen2/)
5. **Use the Knowledge Base.** The crop data from the MCP server is there to make your solution realistic — use it!
6. **Commit often.** Use `git init && git add -A && git commit -m "initial"` early, then commit after each working feature.

---

## 🆘 Troubleshooting

| Problem | Solution |
4. **Check the Amplify docs.** [https://docs.amplify.aws/gen2/](https://docs.amplify.aws/gen2/)
| `aws configure` — command not found | AWS CLI not installed. See Prerequisites. |
| Backend service creation fails | Make sure `aws sts get-caller-identity` works first. Your Workshop Studio credentials may have expired — copy fresh ones. |
| Kiro doesn't see MCP tools | Restart Kiro IDE (or reload window) after editing `.kiro/settings/mcp.json`. |
| `npm create amplify` fails | Make sure Node.js v18+ is installed: `node --version`. |
| Port already in use | Another process is using the port. Kill it or change the port in your dev config. |
| AWS auth errors after a while | Workshop Studio credentials are temporary. Go back and copy new ones. |

---

## 📚 Useful Links
| `npx ampx sandbox` or AWS calls fail | Make sure `aws sts get-caller-identity` works first. Your Workshop Studio credentials may have expired — copy fresh ones. |
- [AWS Amplify Gen2 Docs](https://docs.amplify.aws/gen2/)
- [Kiro IDE Downloads](https://kiro.dev/downloads)
- [AWS Free Tier Info](https://aws.amazon.com/free/)
- [Node.js Downloads](https://nodejs.org)
- [Strands Agents SDK (GitHub)](https://github.com/strands-agents/sdk-python)
- [Strands Agents Documentation](https://strandsagents.com)

---

Good luck, and may your Martian crops thrive! 🌱🚀
