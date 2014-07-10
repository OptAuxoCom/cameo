# Copyright 2014 Novo Nordisk Foundation Center for Biosustainability, DTU.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from Queue import Empty
import traceback
from uuid import uuid4
from cameo.parallel import RedisQueue


class AbstractParallelObserver(object):
    def __init__(self, number_of_islands=None, *args, **kwargs):
        assert isinstance(number_of_islands, int)
        super(AbstractParallelObserver, self).__init__(*args, **kwargs)
        self.queue = RedisQueue(name=uuid4(), namespace=self.__class__)
        self.clients = {}
        self.run = True
        for i in xrange(number_of_islands):
            self._create_client(i)

    def _create_client(self, i):
        raise NotImplementedError

    def _listen(self):
        while self.run:
            try:
                message = self.queue.get(block=True, timeout=5)
                self._process_message(message)
            except Empty:
                pass
            except Exception as e:
                print e
                print traceback.format_exc()

    def _process_message(self, message):
        raise NotImplementedError

    def start(self):
        t = Thread(target=self._listen)
        t.start()

    def finish(self):
        self.run = False


class AbstractParallelObserverClient(object):
    def __init__(self, index=None, queue=None, *args, **kwargs):
        assert isinstance(index, int)
        super(AbstractParallelObserverClient, self).__init__(*args, **kwargs)
        self.index = index
        self._queue = queue

    def __call__(self, population, num_generations, num_evaluations, args):
        raise NotImplementedError

    def reset(self):
        pass

from threading import Thread
from ipython_notebook_utils import ProgressBar as IPythonProgressBar
from blessings import Terminal
from progressbar import ProgressBar as CLIProgressBar, Percentage, Bar, RotatingMarker


class CliMultiprocessProgressObserver(AbstractParallelObserver):
    """
    Command line progress display for multiprocess run
    """
    def __init__(self, *args, **kwargs):
        self.progress = {}
        self.terminal = Terminal()
        super(CliMultiprocessProgressObserver, self).__init__(*args, **kwargs)

    def _create_client(self, i):
        self.clients[i] = CliMultiprocessProgressObserverClient(index=i, queue=self.queue)

    def _process_message(self, message):
        i = message['index']
        if not i in self.progress:
            print ""
            label = "Island %i" % i
            writer = self.TerminalWriter((self.terminal.height or 1) - 1, self.terminal)
            self.progress[i] = CLIProgressBar(fd=writer,
                                              maxval=message['max_evaluations'],
                                              widgets=[label, Percentage(), Bar(marker=RotatingMarker())])
            self.progress[i].start()

        self.progress[i].update(message['num_evaluations'])

    def _listen(self):
        AbstractParallelObserver._listen(self)
        for i, progress in self.progress.iteritems():
            progress.finish()

    class TerminalWriter(object):
        """
        Writer wrapper to write the progress in a specific terminal position
        """
        def __init__(self, pos, term):
            self.pos = pos
            self.term = term

        def write(self, string):
            with self.term.location(0, self.pos):
                print(string)


class CliMultiprocessProgressObserverClient(AbstractParallelObserverClient):

    __name__ = "CLI Multiprocess Progress Observer"

    def __init__(self, *args, **kwargs):
        super(CliMultiprocessProgressObserverClient, self).__init__(*args, **kwargs)

    def __call__(self, population, num_generations, num_evaluations, args):
        self._queue.put_nowait({
            'index': self.index,
            'num_evaluations': num_evaluations,
            'max_evaluations': args.get('max_evaluations', 50000)
        })

    def reset(self):
        pass


class IPythonNotebookMultiprocessProgressObserver(AbstractParallelObserver):
    """
    IPython Notebook Progress Observer for multiprocess run
    """

    def __init__(self, color_map=None, *args, **kwargs):
        self.progress = {}
        self.color_map = color_map
        super(IPythonNotebookMultiprocessProgressObserver, self).__init__(*args, **kwargs)

    def _create_client(self, i):
        self.clients[i] = IPythonNotebookMultiprocessProgressObserverClient(queue=self.queue, index=i)
        label = "<span style='color:%s;'>Island %i </span>" % (self.color_map[i], i+1)
        self.progress[i] = IPythonProgressBar(label=label)

    def _process_message(self, message):
        if self.progress[message['index']].id is None:
            self.progress[message['index']].start()
        self.progress[message['index']].set(message['progress'])


class IPythonNotebookMultiprocessProgressObserverClient(AbstractParallelObserverClient):

    __name__ = "IPython Notebook Multiprocess Progress Observer"

    def __init__(self, *args, **kwargs):
        super(IPythonNotebookMultiprocessProgressObserverClient, self).__init__(*args, **kwargs)

    def __call__(self, population, num_generations, num_evaluations, args):
        p = (float(num_evaluations) / float(args.get('max_evaluations', 50000))) * 100.0
        try:
            self._queue.put_nowait({'progress': p, 'index': self.index})
        except Exception:
            pass

    def reset(self):
        pass