"""
Integration tests for Redis cache service.
"""

import pytest
import subprocess
import time


def get_container_name(service_name):
    """Get the full container name for a docker-compose service."""
    try:
        command = f"docker-compose -f docker-compose.infrastructure.yml ps -q {service_name}"
        container_id = subprocess.check_output(command, shell=True, text=True).strip()
        if not container_id:
            pytest.fail(f"Could not find a running container for service '{service_name}'")
        return container_id
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Error getting container ID for '{service_name}': {e.stderr}")


REDIS_CONTAINER_NAME = get_container_name("redis")


def run_redis_command(redis_command):
    """Run a redis-cli command inside the redis container."""
    command = f"docker exec {REDIS_CONTAINER_NAME} redis-cli {redis_command}"
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        check=False
    )
    if result.returncode != 0:
        pytest.fail(
            f"Redis command failed: {command}
"
            f"Stderr: {result.stderr}
"
            f"Stdout: {result.stdout}"
        )
    return result.stdout.strip()


@pytest.fixture(scope="function", autouse=True)
def cleanup_redis():
    """Ensure the test key is not present before and after each test."""
    run_redis_command("DEL test_cache_key")
    yield
    run_redis_command("DEL test_cache_key")


@pytest.mark.integration
def test_redis_deduplication():
    """
    Tests the TTL-based deduplication pattern using SETEX and EXISTS.
    Requirement: CACH-01
    """
    # 1. Set a key with a 5-second TTL
    setex_cmd = 'SETEX test_cache_key 5 "processed"'
    result = run_redis_command(setex_cmd)
    assert result == "OK", "SETEX command should return OK."

    # 2. Immediately check if the key exists
    exists_cmd = "EXISTS test_cache_key"
    result = run_redis_command(exists_cmd)
    assert result == "1", "Key should exist immediately after setting."

    # 3. Wait for the key to expire
    time.sleep(6)

    # 4. Check if the key still exists
    result = run_redis_command(exists_cmd)
    assert result == "0", "Key should not exist after TTL expiration."
