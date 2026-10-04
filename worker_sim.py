"""
Worker Process Simulator
Executes a single isolated worker step in its own OS process.
"""
import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import config
import database

def step1():
    pid = os.getpid()
    database.init_db()
    database.set_task_state('tour', is_running=True, status=f'Worker-1 (PID {pid}): Running Batch Alpha', current_post_summary='Post 101')
    p_id = database.add_post('tour', f'Multi-worker test post from PID {pid}', 'img_w1.jpg')
    print(json.dumps({'worker': 'Worker-1', 'pid': pid, 'success': True, 'post_id': p_id}))

def step2():
    pid = os.getpid()
    database.init_db()
    state = database.get_task_state('tour')
    if not state or not state['is_running']:
        print(json.dumps({'worker': 'Worker-2', 'pid': pid, 'success': False, 'error': f'tour not running: {state}'}))
        sys.exit(1)
    if 'Worker-1' not in state['status']:
        print(json.dumps({'worker': 'Worker-2', 'pid': pid, 'success': False, 'error': f'Worker-1 not in status: {state["status"]}'}))
        sys.exit(1)
    
    database.set_task_state('nz', is_running=True, status=f'Worker-2 (PID {pid}): Running NZ Sync')
    print(json.dumps({'worker': 'Worker-2', 'pid': pid, 'success': True, 'read_status': state['status']}))

def step3():
    pid = os.getpid()
    database.init_db()
    tour_state = database.get_task_state('tour')
    nz_state = database.get_task_state('nz')
    if not tour_state or not tour_state['is_running'] or not nz_state or not nz_state['is_running']:
        print(json.dumps({'worker': 'Worker-3', 'pid': pid, 'success': False, 'error': 'pre-conditions failed'}))
        sys.exit(1)
    
    database.set_task_state('tour', is_running=False, status=f'Worker-3 (PID {pid}): Stopped')
    print(json.dumps({'worker': 'Worker-3', 'pid': pid, 'success': True}))

if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if action == 'step1':
        step1()
    elif action == 'step2':
        step2()
    elif action == 'step3':
        step3()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
