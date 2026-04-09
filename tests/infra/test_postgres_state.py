"""
Integration tests for PostgreSQL service state management.
"""

import pytest
import subprocess


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


POSTGRES_CONTAINER_NAME = get_container_name("postgres")


def run_postgres_command(sql_command, expect_fail=False):
    """Run a psql command inside the postgres container."""
    command = f"docker exec {POSTGRES_CONTAINER_NAME} psql -U app -d man2cat -c "{sql_command}""
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        check=False
    )
    if not expect_fail and result.returncode != 0:
        pytest.fail(
            f"Postgres command failed: {command}
"
            f"Stderr: {result.stderr}
"
            f"Stdout: {result.stdout}"
        )
    return result


@pytest.fixture(scope="function", autouse=True)
def cleanup_db():
    """Ensure the test table is clean before and after each test."""
    run_postgres_command("DELETE FROM processed_images WHERE s3_bucket = 'test';")
    yield
    run_postgres_command("DELETE FROM processed_images WHERE s3_bucket = 'test';")


@pytest.mark.integration
def test_postgres_unique_constraint():
    """
    Tests that the unique constraint on (s3_bucket, s3_key) in the
    processed_images table is enforced.
    Requirement: STATE-01
    """
    # 1. Insert a record
    insert_cmd = "INSERT INTO processed_images (s3_bucket, s3_key) VALUES ('test', 'image.jpg') RETURNING id;"
    run_postgres_command(insert_cmd)

    # 2. Verify the record exists
    select_cmd = "SELECT COUNT(*) FROM processed_images WHERE s3_bucket='test' AND s3_key='image.jpg';"
    result = run_postgres_command(select_cmd)
    # The output format is like:
    #  count 
    # -------
    #      1
    # (1 row)
    # We just need to check if '1' is in the output.
    assert '1' in result.stdout, "The first record was not inserted correctly."

    # 3. Attempt to insert the same record again, expecting failure
    result_fail = run_postgres_command(insert_cmd, expect_fail=True)
    assert result_fail.returncode != 0, "Second insert should have failed but it succeeded."
    assert "duplicate key value violates unique constraint" in result_fail.stderr, "Error message should indicate a unique constraint violation."

    # 4. Verify that the count is still 1
    result_final_count = run_postgres_command(select_cmd)
    assert '1' in result_final_count.stdout, "The count should still be 1 after the failed insert."
