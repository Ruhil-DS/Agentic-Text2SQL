# Agentic Text2SQL

An end-to-end agentic AI system for converting natural language questions into SQL queries, executing them against a PostgreSQL database, and summarizing the results using Large Language Models.

## Overview

This application allows users to query databases using natural language. It leverages Large Language Models to translate natural language into SQL, validates the SQL for safety, executes it against a PostgreSQL database, and summarizes the results in natural language.

## Features

- Natural language to SQL conversion using OpenAI's GPT models
- SQL validation and safety checks to prevent SQL injection
- Automatic SQL debugging and fixing using an agentic SQL agent
- Result summarization for easier understanding
- Authentication and authorization via JWT tokens
- Customer-specific credentials and API keys stored in MongoDB
- Customizable prompts stored in MongoDB collections
- Containerized deployment with Docker

## Architecture

1. User submits a natural language query via REST API
2. LLM generates SQL based on database schema and query
3. SQL Agent validates and fixes the SQL if needed
4. Query is executed against PostgreSQL
5. Results are summarized by LLM
6. Response is returned to the user

## Getting Started

### Prerequisites

- Docker and Docker Compose (for containerized deployment)
- MongoDB database (the project uses MongoDB Atlas by default)
- PostgreSQL database (for executing SQL queries)
- OpenAI API key

### Setup

1. Clone the repository
```bash
git clone <repository-url>
cd Agentic_Text2SQL
```

2. Set up the environment file
   - The project includes an `env_file` template
   - For local development, copy `env_file` to `.env`
   - Update the MongoDB and PostgreSQL connection strings as needed

```bash
cp env_file .env
```

3. Initialize MongoDB with required collections
   - Run the initialization script to set up MongoDB collections and default prompts

```bash
pip install -r initialize_mongodb_requirements.txt
python initialize_mongodb.py
```

4. Start the application

   **Option 1: Run locally**
   ```bash
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```

   **Option 2: Run with Docker**
   ```bash
   docker-compose up -d
   ```

5. The API will be available at `http://localhost:8000`
6. Access the interactive API documentation at `http://localhost:8000/docs`

### Database Setup

The application requires:

1. **MongoDB** for storing:
   - Customer credentials and API keys
   - Custom prompts for SQL generation, debugging, and result summarization

2. **PostgreSQL** database:
   - The default configuration uses a `university` database
   - The application extracts schema information and executes SQL queries against this database

### Creating a Customer

During MongoDB initialization, you'll be prompted to create a test customer. Alternatively, you can create customers using the API:

```bash
curl -X POST "http://localhost:8000/api/v1/customers" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "test_customer",
    "password": "your_password",
    "openai_api_key": "your_openai_api_key",
    "postgres_connection": {
      "username": "postgres",
      "password": "Aa000000",
      "host": "localhost",
      "database": "university"
    }
  }'
```

### Authentication

Get an access token:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test_customer&password=your_password"
```

### Making a Query

Use your access token to make a natural language query:

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How many students are enrolled in each department?"
  }'
```

## Project Structure

```
Agentic_Text2SQL/
├── app/
│   ├── api/             # API routes
│   ├── agents/          # SQL Agent and related components
│   ├── core/            # Core application components
│   ├── db/              # Database clients
│   ├── models/          # Data models
│   ├── services/        # Business logic services
│   └── utils/           # Utility functions
├── tests/               # Unit and integration tests
├── env_file             # Environment variables template
├── initialize_mongodb.py # MongoDB initialization script
├── Dockerfile           # Docker configuration
├── docker-compose.yml   # Docker Compose configuration
├── requirements.txt     # Python dependencies
└── main.py              # Application entry point
```

## Customizing Prompts

The application stores prompts in the MongoDB `prompts` collection. There are three default prompts that can be customized:

1. `sql_system_message` - Used for generating SQL from natural language
2. `sql_debug_system_message` - Used for debugging and fixing SQL errors
3. `result_summary_system_message` - Used for summarizing query results

You can update these prompts via the API or by directly modifying them in MongoDB.

## Extending the Project

### Adding New Agents

The SQL Agent can be extended with additional capabilities:

1. Add new agent methods in `app/agents/sql_agent.py`
2. Integrate them in the query service flow in `app/services/query_service.py`

### Supporting Other Databases

To support other databases:

1. Create a new client in `app/db/`
2. Update the schema retrieval methods
3. Modify SQL generation prompts in the MongoDB `prompts` collection

## Troubleshooting

### Common Issues

1. **Connection errors:** Ensure your MongoDB and PostgreSQL connection strings are correct
2. **Authentication issues:** Verify the customer exists and the password is correct
3. **SQL generation errors:** Check that the database schema is being properly retrieved

### Logs

The application logs are stored in `app.log` and contain detailed information about application operations.

---------------
---------------
## File Walkthrough

### `main.py`
- Creates the FastAPI application
- setups the routes, CORS, port, etc
- Also binds the index.html file for a very basic UI built using HTML/CSS/JS


### `config.py`
- Core file to define the `Settings` class which extends the Pydantic's BaseSetting
- Used to load env variables and check for them before the application startup
- Contains configurable parameters that are used in the application


### `routes.py`
- Defines the API endpoints for the fastAPI application
- Defines various Models which extends PyDantic's BaseModel
   - This validates incoming request data against the model's schema. Also ensures serialization to JSON and type safety.

### `mongo_client.py`
- Helps with the MongoDB setup
- Sets up the connection, helps us get relevant data with the right methods
- Supports CRUD operations

### `postgres_client.py`
- Client file for executing on the SQL query on the database.


### `prompt_initializer.py`
- Helps with initializting LLM prompts


### `auth.py`
- This file handles authentication and authorization for the application.


### `query_service.py`
- responsible for processing natural language queries, converting them into SQL, executing the SQL queries, and returning the results.
- It integrates with various components like the LLM service, SQL agent, and PostgreSQL client.


### `llm_service.py`
- Helps us with the LLM related method callings like loading prompts, generating SQL, summarizing results.


### `sql_Agent.py`
- Once the SQL is generated, it goes to this file for validation
- It first manually detects and fixes some common issues like spelling mistakes in the table names or missing quotes for `LIKE` statements.
- It then proceeds to validate the query for ensuring that we only process read-only queries.
- If the validation fails for some reason, we move on to debigging the query with another LLM call where we fix the issues.
> This is a v1 of my custom sql-agent. Future versions will have better functionalities.



## License

[MIT License](LICENSE) 