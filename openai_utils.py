"""
OpenAI Client Utilities for Synchronous and Asynchronous Operations.

This module provides factory functions for creating properly configured OpenAI clients
with automatic API key management and environment variable loading. It supports both
synchronous and asynchronous client patterns for different use cases.

Key Features:
    - Automatic .env.enc loading from project root using DotenvVault
    - Fallback to plain .env loading from project root
    - Environment variable fallback for API key configuration
    - Synchronous client for blocking operations and legacy code
    - Asynchronous client for high-performance concurrent operations
    - Consistent error handling and validation across client types

Async Communication Architecture:
    The async client enables non-blocking I/O operations essential for high-throughput
    agent systems, allowing multiple concurrent API calls without blocking the event loop.
    This is critical for multi-agent systems where agents need to communicate with
    OpenAI services simultaneously.
"""

import logging
import os
import sys
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv
from config_utils import ROOT_FOLDER
from dotenv_crypt import DotenvVault

logger = logging.getLogger(__name__)


ENCRYPTED_ENV_PATH = os.path.join(ROOT_FOLDER, ".env.enc")
PLAIN_ENV_PATH = os.path.join(ROOT_FOLDER, ".env")


def _get_openai_key_path() -> str:
    return os.getenv("OPENAI_KEY_PATH", "/Users/lorenzo/Sync/Tech/Keys/openai.key")


def _load_api_key_to_environ() -> str | None:
    """Load OPENAI_API_KEY into os.environ from encrypted or plain dotenv.

    Load order:
    1) ROOT_FOLDER/.env.enc via DotenvVault and external key file
    2) ROOT_FOLDER/.env via python-dotenv fallback (if key still missing)

    Returns
    -------
    str | None
        OPENAI_API_KEY value if available after loading attempts, otherwise None.
    """
    logger.debug(f"Loading API key from encrypted env: {ENCRYPTED_ENV_PATH}")
    try:
        vault = DotenvVault(_get_openai_key_path())
        vault.load_to_environ(ENCRYPTED_ENV_PATH)
        logger.info("Loaded environment variables from .env.enc")
    except Exception as e:
        logger.debug(f"Failed to load from .env.enc: {e}")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        logger.debug(f"API key not in encrypted env, trying .env: {PLAIN_ENV_PATH}")
        try:
            load_dotenv(dotenv_path=PLAIN_ENV_PATH)
            logger.info("Loaded environment variables from .env")
        except Exception as e:
            logger.debug(f"Failed to load from .env: {e}")
        api_key = os.environ.get("OPENAI_API_KEY")

    if api_key and api_key.strip():
        normalized_api_key = api_key.strip()
        os.environ["OPENAI_API_KEY"] = normalized_api_key
        logger.info("OPENAI_API_KEY loaded successfully")
        logger.debug(f"API key prefix: {normalized_api_key[:10]}...")
        return normalized_api_key

    logger.error("OPENAI_API_KEY not found in any source")
    return None


def get_openai_client() -> OpenAI:
    """
    Create and configure a synchronous OpenAI client with automatic API key loading.

    This function provides a factory method for creating synchronous OpenAI clients
    with proper configuration and validation. It handles API key loading from both
    .env files and environment variables with appropriate error handling.

    Configuration Process:
        1. Load environment variables from ROOT_FOLDER/.env.enc
        2. Fallback to ROOT_FOLDER/.env if API key is still missing
        3. Retrieve OPENAI_API_KEY from os.environ
        4. Validate API key presence and content
        5. Create and return configured OpenAI client

    Returns:
        OpenAI: Configured synchronous OpenAI client ready for API calls.
               Suitable for blocking operations and traditional request-response patterns.

    Raises:
        SystemExit: If OPENAI_API_KEY is not found, empty, or contains only whitespace.
                   The process exits with code 1 to prevent invalid API usage.

    Use Cases:
        - Legacy code requiring synchronous OpenAI operations
        - Simple scripts with sequential API call patterns
        - Testing and development where blocking behavior is acceptable
        - Integration with synchronous frameworks and libraries

    Warning:
        This client performs blocking I/O operations that can stall event loops
        and prevent concurrent execution. For async applications, prefer
        get_async_openai_client() for better performance and concurrency.

    Example:
        ```python
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        ```
    """
    logger.info("Creating synchronous OpenAI client")
    api_key = _load_api_key_to_environ()
    if api_key is None:
        logger.error("[FATAL] OPENAI_API_KEY is not defined in environment! Aborting.")
        print(
            "[FATAL] OPENAI_API_KEY is not defined in environment! Aborting.",
            file=sys.stderr,
        )
        sys.exit(1)
    logger.info("Synchronous OpenAI client created successfully")
    return OpenAI(api_key=api_key)


def get_async_openai_client() -> AsyncOpenAI:
    """
    Create and configure an asynchronous OpenAI client for concurrent operations.

    This function provides a factory method for creating AsyncOpenAI clients optimized
    for high-performance concurrent operations. The async client enables non-blocking
    I/O operations essential for modern agent-based systems and concurrent workflows.

    Configuration Process:
        1. Load environment variables from ROOT_FOLDER/.env.enc
        2. Fallback to ROOT_FOLDER/.env if API key is still missing
        3. Retrieve OPENAI_API_KEY from os.environ
        4. Validate API key presence and content
        5. Create and return configured AsyncOpenAI client

    Returns:
        AsyncOpenAI: Configured asynchronous OpenAI client ready for concurrent API calls.
                    Supports async/await patterns and non-blocking I/O operations.

    Raises:
        SystemExit: If OPENAI_API_KEY is not found, empty, or contains only whitespace.
                   The process exits with code 1 to prevent invalid API usage.

    Async Communication Benefits:
        - Non-blocking I/O: API calls don't block the event loop
        - Concurrent execution: Multiple API calls can run simultaneously
        - Improved throughput: Better resource utilization in high-load scenarios
        - Event loop integration: Seamless integration with asyncio-based applications
        - Scalability: Supports high-concurrency agent communication patterns

    Use Cases:
        - Multi-agent systems requiring concurrent LLM communications
        - High-throughput API processing with multiple parallel requests
        - Real-time applications where blocking would degrade performance
        - Microservices architectures with async communication patterns
        - Agent pools processing multiple tasks concurrently

    Performance Considerations:
        - Significantly better performance for concurrent workloads
        - Lower resource usage compared to thread-based synchronous patterns
        - Proper integration with asyncio event loops and coroutines
        - Supports request batching and concurrent processing patterns

    Example:
        ```python
        async def process_messages():
            client = get_async_openai_client()

            # Single async call
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello!"}]
            )

            # Concurrent calls for better throughput
            tasks = [
                client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": f"Question {i}"}]
                )
                for i in range(5)
            ]
            responses = await asyncio.gather(*tasks)
        ```

    Agent Integration:
        This client is specifically designed for use in agent architectures where
        multiple agents may need to communicate with OpenAI services concurrently.
        It enables efficient message passing, parallel processing, and responsive
        agent behavior in complex multi-agent workflows.
    """
    logger.info("Creating asynchronous OpenAI client")
    api_key = _load_api_key_to_environ()
    if api_key is None:
        logger.error("[FATAL] OPENAI_API_KEY is not defined in environment! Aborting.")
        print(
            "[FATAL] OPENAI_API_KEY is not defined in environment! Aborting.",
            file=sys.stderr,
        )
        sys.exit(1)
    logger.info("Asynchronous OpenAI client created successfully")
    return AsyncOpenAI(api_key=api_key)


def get_openai_api_key() -> str | None:
    """
    Retrieve the OpenAI API key using the same environment loading logic as the clients.

    This function provides access to the OpenAI API key for validation and testing
    purposes without creating a full client instance. It uses the same environment
    variable loading process as get_openai_client() and get_async_openai_client()
    to ensure consistency.

    Configuration Process:
        1. Load environment variables from ROOT_FOLDER/.env.enc
        2. Fallback to ROOT_FOLDER/.env if API key is still missing
        3. Retrieve OPENAI_API_KEY from os.environ
        4. Return the key (or None if not found)

    Returns:
        str | None: The OpenAI API key if found and non-empty, None otherwise.
                   This allows callers to check for API key presence without
                   triggering system exit behavior.

    Use Cases:
        - Environment validation and testing
        - Configuration checks before client creation
        - Debugging and diagnostics
        - Conditional logic based on API key availability

    Example:
        ```python
        api_key = get_openai_api_key()
        if api_key:
            print("✅ OpenAI API key is configured")
        else:
            print("❌ OpenAI API key is missing")
        ```
    """
    return _load_api_key_to_environ()
