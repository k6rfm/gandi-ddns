
ERROR = 0                   # something is wrong
ACTION = 1                  # successful completion, doing something
NOACTION = 2                # successful completeion, doing nothing
INFO = 3                    # information about progress

class Msg:

    def setlevel(self,level):
        self.msglevel = int(level)
        self.msglevel = min(max(self.msglevel,0),3)

    def put(self, level, message):
        if level <= self.msglevel:
            print(message)
