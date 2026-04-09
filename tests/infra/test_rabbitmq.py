"""
Integration tests for RabbitMQ service.
"""

import os
import pytest
import subprocess
import asyncio
import aio_pika

RABBITMQ_CONTAINER_NAME = "rabbitmq"


def run_command(command):
    """Run a shell command and return its output."""
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        check=False
    )
    if result.returncode != 0:
        print(f"Error running command: {command}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")
        pytest.fail(
            f"Command failed with exit code {result.returncode}: {command}
"
            f"Stderr: {result.stderr}"
        )
    return result.stdout.strip()


@pytest.fixture(scope="module")
def rabbitmq_is_healthy():
    """Fixture to ensure RabbitMQ is healthy before running tests."""
    command = f"docker ps --filter 'name={RABBITMQ_CONTAINER_NAME}' --format '{{{{.Status}}}}'"
    status = run_command(command)
    if "healthy" not in status:
        pytest.fail("RabbitMQ container is not healthy.")
    
    # Check diagnostics
    run_command(f"docker exec {RABBITMQ_CONTAINER_NAME} rabbitmq-diagnostics -q ping")


@pytest.mark.integration
def test_rabbitmq_connection(rabbitmq_is_healthy):
    """
    Verifies that a connection to RabbitMQ can be established.
    Requirement: QUEUE-01
    """
    try:
        run_command(f"docker exec {RABBITMQ_CONTAINER_NAME} rabbitmq-diagnostics -q ping")
    except Exception as e:
        pytest.fail(f"RabbitMQ connection test failed: {e}")


@pytest.mark.integration
async def test_dlq_routing():
    """
    Tests that a rejected message is routed to the Dead Letter Queue.
    Requirement: QUEUE-02
    """
    user = os.getenv("RABBITMQ_USER", "app")
    password = os.getenv("RABBITMQ_PASS", "secure_password")
    host = os.getenv("RABBITMQ_HOST", "localhost")
    
    try:
        connection = await aio_pika.connect_robust(f"amqp://{user}:{password}@{host}/")
    except Exception as e:
        pytest.fail(f"Could not connect to RabbitMQ: {e}")
        
    async with connection:
        channel = await connection.channel()
        
        # Declare a test queue with DLX configuration
        dlq_name = 'test_dlq_queue'
        queue_name = 'test_main_queue'
        
        dlq = await channel.declare_queue(dlq_name, durable=True)
        
        # Declare main queue and bind DLQ to it
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                'x-dead-letter-exchange': '', # Default exchange
                'x-dead-letter-routing-key': dlq_name
            }
        )

        # Purge queues to ensure they are empty
        await queue.purge()
        await dlq.purge()

        # Publish a message to the main queue
        message_body = b'This is a test message for DLQ routing'
        await channel.default_exchange.publish(
            aio_pika.Message(body=message_body),
            routing_key=queue_name
        )

        # Consume the message and reject it
        incoming_message = await queue.get(timeout=5)
        assert incoming_message is not None, "Message was not published to the main queue."
        await incoming_message.reject(requeue=False)

        # Check if the message is now in the DLQ
        dlq_message = await dlq.get(timeout=5)
        assert dlq_message is not None, "Message was not routed to the DLQ."
        assert dlq_message.body == message_body, "DLQ message body does not match."
        
        # Clean up
        await queue.delete()
        await dlq.delete()
