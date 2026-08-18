import os
import multiprocessing
import sys

class NoConsoleProcess(multiprocessing.Process):
    def __init__(self, *args, **kwargs):
        '''
        if hasattr(multiprocessing, 'get_all_start_methods') and 'spawn' in multiprocessing.get_all_start_methods():
            # If running on Windows
            kwargs['start_method'] = 'spawn'
        '''
        super().__init__(*args, **kwargs)
        self.queue = multiprocessing.Queue()

    def run(self):
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')
        try:
            super().run()
        except Exception as e:
            self.queue.put(('error', str(e)))
        else:
            self.queue.put(('done', None))
