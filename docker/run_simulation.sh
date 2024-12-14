#!/bin/bash

# Constants
OUTPUT_DIR="outputs"
SIMULATION_SCRIPT="./start-simulator.sh"
RECEIVER_READY_MESSAGE="Receiver running"
NUM_RUNS=10
CLEANUP_FILE="hdd/file2.mp3"

# Ensure the output directory exists
mkdir -p "$OUTPUT_DIR"

# Function to start and wait for the receiver to be ready
start_and_wait_for_receiver() {
    nohup $SIMULATION_SCRIPT > simulator.log 2>&1 &  # Run simulation in the background
    simulator_pid=$!  # Capture the PID of the background process
    echo "Simulator PID: $simulator_pid"
    sleep 2  # Give some time for the simulator to initialize

    echo "Waiting for receiver to be ready..."
    while true; do
        if grep -q "$RECEIVER_READY_MESSAGE" simulator.log; then
            echo "Receiver is running!"
            break
        fi
        sleep 1  # Avoid busy-waiting
    done
}

# Function to run the Python sender script
run_sender_script() {
    local script_name=$1
    local output_file="$OUTPUT_DIR/${script_name##*/}.out"

    echo "Running $script_name..."
    python3 "$script_name" >> "$output_file" 2>&1 || {
        echo "Error running $script_name"
        exit 1
    }

    # Clean up the generated file2.txt file after each run
    if [ -f "$CLEANUP_FILE" ]; then
        echo "Cleaning..."
        rm -f "$CLEANUP_FILE"
    fi
}

# Main execution
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <python_script>"
    exit 1
fi

script=$1

# Run simulation and sender script NUM_RUNS times
for ((run = 1; run <= NUM_RUNS; run++)); do
    echo "Run #$run of $script..."
    
    # Start the receiver and wait for it to be ready
    start_and_wait_for_receiver
    
    # Run the sender script
    run_sender_script "$script"

    sleep 2  # Wait a moment to ensure the simulator is fully stopped
done

echo "All runs completed."
