"""Web Dashboard for Gamma Scalping System"""

import json
import logging
import os
import time

from flask import Flask, jsonify, render_template, request

from gamma_scalping.bot_controller import BotController

app = Flask(__name__)
controller = BotController()


@app.route('/')
def index():
   return render_template('index.html')


@app.route('/api/state')
def api_state():
   state = controller.get_state()
   state['running'] = controller.is_running
   return jsonify(state)


@app.route('/api/logs')
def api_logs():
   since = request.args.get('since', type=float, default=0)
   logs = controller.get_logs(since)
   return jsonify({'logs': logs, 'now': time.time()})


@app.route('/api/start', methods=['POST'])
def api_start():
   success = controller.start()
   return jsonify({'success': success})


@app.route('/api/stop', methods=['POST'])
def api_stop():
   controller.stop()
   return jsonify({'success': True})


@app.route('/api/close', methods=['POST'])
def api_close():
   controller.close_all()
   return jsonify({'success': True})


@app.route('/api/restart', methods=['POST'])
def api_restart():
   controller.stop()
   time.sleep(1)
   success = controller.start()
   return jsonify({'success': success})


if __name__ == '__main__':
   print('Starting Gamma Scalping Web Dashboard...')
   print('Open http://127.0.0.1:5000 in your browser')
   app.run(debug=False, host='127.0.0.1', port=5000)
