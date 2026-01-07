#!/usr/bin/env python3
"""
Bursty Training Workload for Ray Cluster
Demonstrates autoscaling behavior with deterministic burst patterns
"""

import ray
import time
import json
import numpy as np
from datetime import datetime
from typing import Dict, List
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@ray.remote
class WorkerTask:
    """Ray remote task that simulates ML training work"""
    
    def __init__(self, task_id: int):
        self.task_id = task_id
        self.start_time = time.time()
    
    def compute_intensive_work(self, duration: float, size: int) -> Dict:
        """
        Simulate compute-intensive ML training work
        
        Args:
            duration: How long to work (seconds)
            size: Problem size (affects memory and CPU)
        
        Returns:
            Dictionary with task metrics
        """
        start = time.time()
        
        # Simulate matrix operations (common in ML)
        matrix_a = np.random.rand(size, size)
        matrix_b = np.random.rand(size, size)
        
        # Perform computation until duration is reached
        iterations = 0
        while time.time() - start < duration:
            result = np.dot(matrix_a, matrix_b)
            # Add some variance to prevent optimization
            matrix_a = result / np.max(result) if np.max(result) > 0 else matrix_a
            iterations += 1
        
        elapsed = time.time() - start
        
        return {
            'task_id': self.task_id,
            'iterations': iterations,
            'elapsed_seconds': elapsed,
            'matrix_size': size,
            'timestamp': datetime.utcnow().isoformat()
        }


class BurstyWorkloadOrchestrator:
    """Orchestrates bursty workload patterns for autoscaling demonstration"""
    
    def __init__(self):
        self.metrics: List[Dict] = []
        
    def log_metrics(self, phase: str, workers: int, tasks: int, latency: float, cost_proxy: float):
        """Log structured metrics for analysis"""
        metric = {
            'timestamp': datetime.utcnow().isoformat(),
            'phase': phase,
            'workers': workers,
            'tasks': tasks,
            'latency_seconds': latency,
            'cost_proxy_units': cost_proxy
        }
        self.metrics.append(metric)
        logger.info(json.dumps(metric))
    
    def run_workload_phase(self, phase_name: str, num_tasks: int, task_duration: float, 
                          matrix_size: int) -> float:
        """
        Run a single phase of the workload
        
        Args:
            phase_name: Name of the phase for logging
            num_tasks: Number of parallel tasks to launch
            task_duration: Duration for each task
            matrix_size: Size of matrices for computation
        
        Returns:
            Total phase latency in seconds
        """
        logger.info(f"Starting phase: {phase_name} with {num_tasks} tasks")
        phase_start = time.time()
        
        # Create worker tasks
        workers = [WorkerTask.remote(i) for i in range(num_tasks)]
        
        # Launch all tasks in parallel
        futures = [worker.compute_intensive_work.remote(task_duration, matrix_size) 
                  for worker in workers]
        
        # Wait for all tasks to complete
        results = ray.get(futures)
        
        phase_latency = time.time() - phase_start
        
        # Calculate cost proxy (worker-seconds)
        cost_proxy = num_tasks * task_duration
        
        # Log phase metrics
        self.log_metrics(
            phase=phase_name,
            workers=num_tasks,
            tasks=len(results),
            latency=phase_latency,
            cost_proxy=cost_proxy
        )
        
        logger.info(f"Phase {phase_name} completed in {phase_latency:.2f}s")
        return phase_latency
    
    def run_burst_pattern(self):
        """
        Execute deterministic burst pattern
        
        Pattern:
        1. Idle period (scale down)
        2. Small burst (scale up slowly)
        3. Peak burst (full scale up)
        4. Sustained load (maintain scale)
        5. Gradual decrease (scale down)
        6. Idle period (minimum scale)
        """
        
        logger.info("="*80)
        logger.info("BURSTY TRAINING WORKLOAD - Ray Autoscaling Demonstration")
        logger.info("="*80)
        
        # Phase 1: Warm-up (small load)
        logger.info("\n📊 Phase 1: Warm-up")
        time.sleep(5)  # Give cluster time to initialize
        self.run_workload_phase(
            phase_name="warmup",
            num_tasks=2,
            task_duration=10,
            matrix_size=500
        )
        
        # Phase 2: Small burst
        logger.info("\n📊 Phase 2: Small Burst")
        time.sleep(10)  # Allow autoscaler to observe
        self.run_workload_phase(
            phase_name="small_burst",
            num_tasks=5,
            task_duration=15,
            matrix_size=700
        )
        
        # Phase 3: Peak burst (trigger full scale-up)
        logger.info("\n📊 Phase 3: Peak Burst")
        time.sleep(10)
        self.run_workload_phase(
            phase_name="peak_burst",
            num_tasks=10,
            task_duration=20,
            matrix_size=1000
        )
        
        # Phase 4: Sustained high load
        logger.info("\n📊 Phase 4: Sustained Load")
        self.run_workload_phase(
            phase_name="sustained_load",
            num_tasks=8,
            task_duration=15,
            matrix_size=800
        )
        
        # Phase 5: Gradual decrease
        logger.info("\n📊 Phase 5: Gradual Decrease")
        time.sleep(10)
        self.run_workload_phase(
            phase_name="gradual_decrease",
            num_tasks=4,
            task_duration=10,
            matrix_size=600
        )
        
        # Phase 6: Cooldown (trigger scale-down)
        logger.info("\n📊 Phase 6: Cooldown")
        time.sleep(30)  # Allow scale-down to occur
        self.run_workload_phase(
            phase_name="cooldown",
            num_tasks=2,
            task_duration=5,
            matrix_size=400
        )
        
        logger.info("\n✅ Workload pattern complete!")
    
    def print_summary(self):
        """Print summary of all metrics"""
        logger.info("\n" + "="*80)
        logger.info("WORKLOAD SUMMARY")
        logger.info("="*80)
        
        total_tasks = sum(m['tasks'] for m in self.metrics)
        total_cost = sum(m['cost_proxy_units'] for m in self.metrics)
        avg_latency = np.mean([m['latency_seconds'] for m in self.metrics])
        max_workers = max(m['workers'] for m in self.metrics)
        
        logger.info(f"Total tasks executed: {total_tasks}")
        logger.info(f"Total cost proxy (worker-seconds): {total_cost:.2f}")
        logger.info(f"Average phase latency: {avg_latency:.2f}s")
        logger.info(f"Peak workers used: {max_workers}")
        
        logger.info("\nPhase Details:")
        for metric in self.metrics:
            logger.info(
                f"  {metric['phase']:20s} | "
                f"Workers: {metric['workers']:3d} | "
                f"Latency: {metric['latency_seconds']:6.2f}s | "
                f"Cost: {metric['cost_proxy_units']:6.2f}"
            )
        
        logger.info("="*80)
        
        # Calculate autoscaling efficiency
        ideal_cost = total_tasks * 15  # If all tasks ran at exactly their duration
        actual_cost = total_cost
        efficiency = (ideal_cost / actual_cost) * 100 if actual_cost > 0 else 0
        
        logger.info(f"\n💰 Cost Efficiency: {efficiency:.1f}%")
        logger.info(f"   Ideal cost: {ideal_cost:.2f} worker-seconds")
        logger.info(f"   Actual cost: {actual_cost:.2f} worker-seconds")
        
        if efficiency > 90:
            logger.info("   ✅ Excellent autoscaling efficiency!")
        elif efficiency > 75:
            logger.info("   ✔️  Good autoscaling efficiency")
        else:
            logger.info("   ⚠️  Consider tuning autoscaling parameters")


def main():
    """Main entry point"""
    try:
        # Initialize Ray
        logger.info("Connecting to Ray cluster...")
        ray.init(address='auto')
        
        logger.info(f"Ray cluster initialized")
        logger.info(f"Available resources: {ray.available_resources()}")
        logger.info(f"Cluster nodes: {len(ray.nodes())}")
        
        # Run the workload
        orchestrator = BurstyWorkloadOrchestrator()
        orchestrator.run_burst_pattern()
        orchestrator.print_summary()
        
        # Export metrics to JSON
        with open('/tmp/workload-metrics.json', 'w') as f:
            json.dump(orchestrator.metrics, f, indent=2)
        
        logger.info("\n📁 Metrics saved to /tmp/workload-metrics.json")
        
    except Exception as e:
        logger.error(f"Error running workload: {e}", exc_info=True)
        raise
    finally:
        # Cleanup
        ray.shutdown()
        logger.info("Ray connection closed")


if __name__ == "__main__":
    main()
