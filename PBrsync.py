#!/usr/bin/env python

import os
import shutil
import subprocess
import time
import sys
from datetime import datetime
import getopt
import string,random
import ConfigParser

try:
    import simplejson as json
except:
    import json
try:
    from subprocess import DEVNULL # py3k
except ImportError:
    DEVNULL = open(os.devnull, 'wb')

excludeDirs = ['.PBrsync']    # Full (relative) path to exclude directories
excludePaths = []               # Full (relative) path to exclude file
excludeNames = ['.DS_Store']    # Exclude any file with this name
RsyncFlags = ['-hh']
silent = False
ctime_check = False
tmpLogSpace = 0
allow_snap = True
local_backup = True
remote_backup = True
conflictMode  = 'both'

input_parsed = False

log = []

def sync(path='.'):
   
    path = StandardizeFolderPath(path)
    
    global tmpLogSpace
    global lastrun_time
    global Aname,pathA,Bname,pathB
    global rsyncFlags_ALL,pathBrsync
    
    start()
    
    try:
        lastrun_time = float(file(pathA+'.PBrsync/lastrun').read())
    except:
        addLog('Could not load last run time. Using current time (ie, no files modified)')
        lastrun_time = time.time()
    
    ############################ 
    
    # Load the old list
    if not os.path.exists(pathA+'.PBrsync'):
        raise ValueError('Not a PBrsync directory')

    try:
        with open(pathA+'.PBrsync/local_old.list','r') as F:
            oldListA = fileListTXT2objList(F.read())
        with open(pathA+'.PBrsync/remote_old.list','r') as F:
            oldListB = fileListTXT2objList(F.read())
    except:
        print('='*60 + '\nERROR: Must perform `reset-files`, `push`, or `pull` after init\n' + '='*60)
        sys.exit(2)
        
    
    addLog('Parsing local tree for changes and moves')
    curListA = fileListTXT2objList(FileInfoList(pathA,empty='create'))
    

    addLog('Parsing remote tree for changes and moves')
    addLog('  (Also accounting for empty directories)')
 
    fileListB_txt = getB_FileInfoList(empty='create')
    curListB = fileListTXT2objList(fileListB_txt)

    # Process
    
    addLog('Comparing and resolving conflicts')
    moveQueueB,moveQueueA = MovedFileQueue(curListA,oldListA,curListB,oldListB)
    
    addLog('Applying Local Moves:'); tmpLogSpace = 4
    ProcessActionQueue(pathA,moveQueueA,Aname)
    tmpLogSpace = 0
    
    addLog('Applying Remote Moves:'); tmpLogSpace = 4
    B_ProcActQueue(moveQueueB,Bname)
    tmpLogSpace = 0

    addLog(' ')
    addLog('-'*60)

    ## Rsync calls. These need to be build better
    addLog('Running `dry-run` rsync (with delete) for file lists')
    rsyncFlags_ALL =  ['-az','--exclude','.PBrsync','-i'] + RsyncFlags
    rsyncFlags_init = ['--delete','--dry-run',]

    pathBrsync = pathB
    if isBremote:
        pathBrsync = '{:s}:{:s}'.format(B_host,pathB)
    
    A2B = subprocess.check_output(['rsync'] + rsyncFlags_ALL + rsyncFlags_init + [pathA,pathBrsync],stderr=DEVNULL)
    B2A = subprocess.check_output(['rsync'] + rsyncFlags_ALL + rsyncFlags_init + [pathBrsync,pathA],stderr=DEVNULL)
    
   
    addLog(' ')
    addLog('Comparing, resolving conflicts, setting ignore files'); tmpLogSpace = 4
    
    queueA,queueB,excludeA2B,excludeB2A =  CompareRsyncResults(A2B,B2A,curListA,oldListA,curListB,oldListB)

    # From queueA and excludeA2B, we can figure out which files need to be backed up
    if local_backup: 
        # Items to back up
        items = [src for src,dest in queueA if dest is None] + excludeA2B
        items = [i for i in items if i not in conflictProps]
         
        perform_local_backup(items)
    

    tmpLogSpace = 0
    addLog('Applying Local Actions:'); tmpLogSpace = 4
    ProcessActionQueue(pathA,queueA,Aname)
    
    tmpLogSpace = 0
    
    addLog('Applying Remote Actions:'); tmpLogSpace = 4
    
    if remote_backup:
        items = [src for src,dest in queueB if dest is None] + excludeB2A
        items = [i for i in items if i not in conflictProps]
        B_ProcActQueue(queueB,Bname,backupItems=items)
    else: 
        B_ProcActQueue(queueB,Bname)
    

    tmpLogSpace = 0
    
    ################
    
    tmpFile = randomString(10)
    
    rsyncFlag_FINAL = ['-v','--exclude-from',tmpFile,'--exclude',tmpFile]
    
    with open(tmpFile,'w') as F:
        F.write('\n'.join(excludeA2B+excludeDirs+excludeNames+excludePaths))
    A2B = subprocess.check_output(['rsync'] + rsyncFlags_ALL + rsyncFlag_FINAL + [pathA,pathBrsync],stderr=DEVNULL)

    with open(tmpFile,'w') as F:
        F.write('\n'.join(excludeB2A+excludeDirs+excludeNames+excludePaths))

    B2A = subprocess.check_output(['rsync'] + rsyncFlags_ALL + rsyncFlag_FINAL + [pathBrsync,pathA],stderr=DEVNULL)

    os.remove(tmpFile)
    
    tmpLogSpace = 0
    addLog('')
    addLog('-'*60)
    addLog('Final rsync Transfer')
    
    tmpLogSpace = 4
    logRsyncFinal(A2B,B2A)
    tmpLogSpace = 0
    
    cleanup()

def pushpull(path,pushpull,delete=False):
    assert pushpull in ['push','pull']
    
    path = StandardizeFolderPath(path)
    
    global tmpLogSpace
    global lastrun_time
    global Aname,pathA,Bname,pathB
    global rsyncFlags_ALL,pathBrsync
    
    start()
    
    addLog(' ')
    addLog('{:s} mode'.format(pushpull))
    ############################ 
    rsyncFlags_ALL =  ['-az','--exclude','.PBrsync','-i'] + RsyncFlags
    for item in excludeDirs + excludePaths:
        rsyncFlags_ALL.append('--exclude')
        rsyncFlags_ALL.append(item)
        
    pathBrsync = pathB
    if isBremote:
        pathBrsync = '{:s}:{:s}'.format(B_host,pathB)
    
    rsyncFlag_FINAL = []
    if delete:
        rsyncFlag_FINAL.append('--delete')    
    
    if pushpull == 'pull':
        B2A = subprocess.check_output(['rsync'] + rsyncFlags_ALL + rsyncFlag_FINAL + [pathBrsync,pathA],stderr=DEVNULL)
        A2B = ''
    elif pushpull == 'push':
        A2B = subprocess.check_output(['rsync'] + rsyncFlags_ALL + rsyncFlag_FINAL + [pathA,pathBrsync],stderr=DEVNULL)
        B2A = ''
    
    addLog('rsync Transfer')
    tmpLogSpace = 4
    logRsyncFinal(A2B,B2A)
    tmpLogSpace = 0

    cleanup()
def start():
    
    
    global tmpLogSpace
    global lastrun_time
    global Aname,pathA,Bname,pathB
    
    global startTime
    
    startTime = time.time()
    
    tmpLogSpace = 0
    
    
    # Parse Inputs
    if not os.path.exists(path + '.PBrsync/config'):
        
        print('ERROR: {:s} not a PBrsync directory. Printing help'.format(path))
        usage()
        sys.exit(2)
    
    parseInput(path)
    
    pathA = StandardizeFolderPath(pathA)
    pathB = StandardizeFolderPath(pathB)
    
    # Logging
    addLog('#'*60)
    addLog('# PBrsync -- Python-wrapper for Bi-directional rsync')
    addLog('#')
    addLog('#      >>>>> Use at your own risk!!! <<<<<')
    addLog('#')    
    addLog(' ')
    addLog('Date: {:s} ({:s} Unix Time)'.format(datetime.now().strftime('%Y-%m-%d_%H%M%S'),str(startTime)))
    addLog('   A (local): {:s}'.format(pathA))
    if isBremote:
        addLog('   B (Remote): {:s}:{:s}'.format(B_host,pathB))
    else:
        addLog('   B (local): {:s}'.format(pathB))
    addLog(' ')
    addLog('-'*60)
    
def cleanup():
    addLog('')
    addLog('-'*60)
    addLog('Cleanup')
    addLog('')
    addLog('Saving Local Tree')
    
    finalListA_txt = FileInfoList(pathA,empty='delete')
    
    with open(pathA+'.PBrsync/local_old.list','w') as F:
        F.write(finalListA_txt)

    addLog('Saving Remote Tree')
    addLog('  (And removing cruft)')
    
    
    finalListB_txt = getB_FileInfoList(empty='delete')
    
    with open(pathA+'.PBrsync/remote_old.list','w') as F:
        F.write(finalListB_txt)
    
    addLog('Saving last run')
    # Make the `last_run` file minus 5 minutes
    with open(pathA+'.PBrsync/lastrun','w') as F:
        F.write(str(time.time()))
    
    
    addLog('Finished: {:s} seconds'.format(str(time.time() - startTime)))
    
    
    addLog(' ')
    addLog('Saved Log in {:s}'.format(logFile.name),flush=True)
    
    logFile.close()

def checkForDissallowedFlags(): 
    
    short = ['v']
    long = ['verbose','stats']
    
    for flag in RsyncFlags:
        if flag.startswith('-') and any([flag.find(i) != -1 for i in short]):
            print('Dissallowed flag found')
            print('Dissallowed flags are: {:s}'.format(', '.join(short)))
            sys.exit(2)
            
        if flag.startswith('--') and flag[2:] in long:
            print('Dissallowed flag ({:s}) found'.format(flag))
            print('Dissallowed flags are: {:s}'.format(', '.join(long)))
            sys.exit(2)

def parseInput(path):
    
    parser = ConfigParser.SafeConfigParser()
    
    if not os.path.exists(path + '.PBrsync/config'):
        print('Not a PBrsync directory')
        sys.exit(2)
    
    parser.read(path + '.PBrsync/config')

    # Local
    global Aname,pathA
    localConfig = {name:val for name,val in parser.items('local')}
    Aname = localConfig['name'].replace(' ','_')
    pathA = localConfig['path']
    pathA = StandardizeFolderPath(pathA)
    
    if not os.path.exists(pathA):
        print("Specified local path does not exists")
        print("Have you set the config file?")
        sys.exit(2)

    if not os.path.abspath(path) == os.path.abspath(pathA):
        print path
        print pathA
        print("Configured local path does not match function call")
        print("Have you set the config file?")
        sys.exit(2)
        

    # remote
    global Bname,pathB,isBremote
    remoteConfig = {name:val for name,val in parser.items('remote')}
    Bname = remoteConfig['name'].replace(' ','_')
    pathB = remoteConfig['path']

    isBremote = False
    if 'host' in remoteConfig:
        global B_host,B_pathToPBrsync
        isBremote = True 
        B_pathToPBrsync = remoteConfig['pbrsync']
        B_host = remoteConfig['host']
    
    global excludeDirs, excludePaths, excludeNames
    
    for param,val in parser.items('exclusions'):
        if param == 'dir':
            excludeDirs.append(val)
        elif param == 'name':
            excludeNames.append(val)
        elif param == 'path':
            excludePaths.append(val)
        else:
            raise ValueError('Unrecognized `exclusions` type')
    
    global RsyncFlags,check_ctime,allow_snap,local_backup,remote_backup,conflictMode
    
    for param,val in  parser.items('other'):
        if param == 'rsyncflags':
            RsyncFlags.append(val)
        elif param == 'check_ctime':
            check_ctime = val.lower() == 'true'
        elif param == 'conflictmode':
            conflictMode = val.lower()
            if conflictMode not in ['both','newer','a','b']:
                print('Unrecognized conflict mode: {:s}'.format(val))
                sys.exit(2)
        else:
           print('Uncreognized `other` type: {:s}'.format(param))
           sys.exit()
    for param,val in parser.items('backups'):
        if param in ['allow_snap','snapshots']:
            allow_snap = val.lower() == 'true'
        elif param in ['localbackup']:
            local_backup = val.lower() == 'true'
        elif param in ['remotebackup']:
            remote_backup = val.lower() == 'true'
    
    global input_parsed
    input_parsed = True

    if conflictMode != 'both' and  ( (not local_backup) or (not remote_backup)):
        addLog('='*30)
        addLog("WARNING !!!: `conflictMode` is not 'both' and backups are off")
        addLog(' Potential for data loss. Waiting 3 seconds')
        addLog('='*30)
        time.sleep(3)
    
    checkForDissallowedFlags()
    
def addLog(entry,space=0,flush=True):
    global silent
    global log
    global tmpLogSpace
    global logFile
    
    try:
        logFile.mode
    except:
        # Set up logging    
        if not os.path.exists(pathA+'.PBrsync/logs/'):
            os.makedirs(pathA+'.PBrsync/logs/')
        logName = pathA+'.PBrsync/logs/' + datetime.now().strftime('%Y-%m-%d_%H%M%S') + '.log'
        logFile = open(logName,'w')
    
    
    
    entry = ' '*space + ' '*tmpLogSpace +  entry
    
    if not silent:
        print(entry)
    
    log.append(entry)
    logFile.write(entry + '\n')
    
    if flush:
        logFile.flush()

def StandardizeFolderPath(path,check=False):
    """ Add's a `/` is not there and then (optionally) ensures it is a folder"""
    
    if not path.endswith('/'):
        path += '/'
    
    if check and not os.path.isdir(path):
        print('WARNING: Path is not a folder. `{:s}`'.format(path))
    
    return path    

def getB_FileInfoList(empty=None):
    """
    Return the file list for B
    """
    global isBremote, B_host, B_pathToPBrsync,pathB
    global excludeDirs 
    global excludePaths
    global excludeNames

    
    if not isBremote:
        return FileInfoList(pathB,empty=empty)
    
    # Build the command
    cmd = 'ssh -T -q {:s} "{:s} API_listFiles'.format(B_host,B_pathToPBrsync)
    
    for dir in excludeDirs:
        cmd += ' --excludeDir {:s} '.format(dir)
    for path in excludePaths:
        cmd += ' --excludePath {:s} '.format(path)
    for name in excludeNames:
        cmd += ' --excludeName {:s} '.format(name)
    
    cmd += ' ' + pathB + '"'
    
    # The "Proper" way to do this is with `subprocess` but for some reason
    # it does not like the complex remote command. Instead, we send the output
    # to a file and read it. Use `os.system`
    
    tmpFile = randomString(10)
        
    stat = os.system(cmd + ' >& ' + tmpFile) # Add a pipe for error output
    with open(tmpFile,'r') as F:
        fileList = F.read()
    os.remove(tmpFile)
    
    if stat != 0:
        addLog('Could not reach remote host')
        addLog('Check your network connection')
        addLog('Attempted Command:')
        addLog('  $ ' + cmd)
        sys.exit()
    
    # Look for `'>>><<<>>><<<>>><<<>>><<<'` which is at the start of the file
    startIX = fileList.find('>>><<<>>><<<>>><<<>>><<<')
    if startIX >= 0: # Found it
        fileList = fileList[startIX+24:] 
    
    return fileList

def FileInfoList(startPath,empty=None): 
    """
    Recursivly list all files (not folders) starting from the (absolute) startPath.
    
    Returns a list of in the format
        POSIX_mtime <tab> POSIX_inode <tab> RELATIVE_FIlE_NAME

    (tabs are used to you can split on `\t` without concern for spaces in file names
    
    Options:
        empty           :   [None] if it is
                                'create'    - A temp file is created when 
                                              encoundering an empyt directory
                                'delete'    - All temp files are deleted
    """    
    
    global excludeDirs    
    global excludePaths   
    global excludeNames   
    
    startPath = StandardizeFolderPath(startPath)

    full_excludeDirs = [startPath+i for i in excludeDirs]
    
    list = []

    for directory, subDirs, subFiles in os.walk(startPath):

        directory = StandardizeFolderPath(directory,check=False)

        # Remove excluded directories
        full_subDirs = [directory + subDir for subDir in subDirs]
        for excludeDir in excludeDirs:
            full_excludeDir = startPath + excludeDir
            if full_excludeDir in full_subDirs:
                removeDir = os.path.relpath(full_excludeDir,directory)
                del subDirs[subDirs.index(removeDir)]

        if len(subFiles) == 0 and len(subDirs) == 0 and empty =='create':
            with open(directory+'.JWempty','w') as F:
                F.write(str(time.time()))
            subFiles .append('.JWempty')
            
        for file in subFiles:
            fullPath = StandardizeFolderPath(directory,check=False) + file
            relPath = os.path.relpath(fullPath,startPath)
        
            if empty == 'delete' and file.startswith('.JWempty'):
                os.remove(fullPath)
                continue
            
            if relPath in excludePaths:
                continue
        
            if file in excludeNames:
                continue
            
            if os.path.islink(fullPath):
                addLog(' File {:s} is a symbolic link and will not be tracked'.format(relPath))
                continue
            
            stat = os.stat(fullPath)
            
            mtime = time.time()+3600 # Make modification in the future
            inode = 0
            ctime = 0
            try: 
                mtime = stat.st_mtime 
            except: 
                pass
            try: 
                inode = stat.st_ino
            except: 
                pass
            try:
                ctime = stat.st_ctime
            except:
                pass
            
        
            list.append({'mtime':mtime,'inode':inode,'relPath':relPath,'ctime':ctime})
    return json.dumps(list)

def isfileObj(obj):
    """ Returns True of the input is a file object """
    if type(obj) is type(fileObj('','','')):
        return True
    return False
    

class fileObj(object):
    def __init__(self,path,inode,mtime,ctime=None):
        global lastrun_time
        
        self.path = path
        self.inode = inode
        self.mtime = mtime
        self.ctime = ctime

        
        if self.mtime > lastrun_time:
            self.modified = True
        else:
            self.modified = False
        
    def __repr__(self):
        mod = 'modified'
        if not self.modified:
            mod = 'un-' + mod 
        return 'm{:17.4f}\tc{:17.4f}\t{:15d}\t{:s}\t{:s}\n'.format(self.mtime,self.ctime,self.inode,self.path,mod) 

def fileListTXT2objList(fileList):
    """ Turn file lists into list of objects """
    fileList = byteify(json.loads(fileList))
    
    objList = []
    for file in fileList:
        
        ctime = float(file['ctime'])
        mtime = float(file['mtime'])
        inode = float(file['inode']); 
        path = file['relPath']
        
        if path.endswith('.JWempty'): continue
        
        objList.append(fileObj(path,inode,mtime,ctime))
    return objList

def movedFileDict(curList,oldList):
    """
    Return a dictionary of moved files where the key is the old path (so that
    you can match them) and the value is the new path
    
    """        
    # Make old into dictionary by inode. Recall that the objects are pointers
    oldList_inode = {file.inode:file for file in oldList}  


    # Recall
    #     if a in D.keys()
    # is O(N) while
    #     if a in D
    # is O(1) and is the same. Makes this O(N) instead of O(N^2) on average

    # Find if the paths have changed. We use the curList and not a dictionary 
    # version since we care about the order
    movedDict = {}
    for file in curList[::-1]:
        if file.inode not in oldList_inode: # New file or not found
            continue
            
        if file.path == oldList_inode[file.inode].path: # Not moved
            continue
    
        if ctime_check and abs(oldList_inode[file.inode].ctime - file.ctime) > 1:
            addLog('Matched inode but unmatched ctime: {:s},{:s}. Skip'.format(oldList_inode[file.inode].path,file.path))
            continue
        
        if file.path.endswith('.JWempty'):
            # This is a special case for the test run where things are created too soon
            addLog('Skipped a "move" that was likely fake')
            addLog('   {:s} --> {:s}'.format(oldList_inode[file.inode].path,file.path))
            continue
        
        movedDict[oldList_inode[file.inode].path] = file.path
        
    return movedDict

def MovedFileQueue(curListA,oldListA,curListB,oldListB):
    """
    Generate a queue to move files before sync lists. The incoming lists will 
    get modified in place with new locations
    """
    moved_Local = movedFileDict(curListA,oldListA)
    moved_Remote = movedFileDict(curListB,oldListB)

    # First parse local moves
    moveQueueB = []
    moveQueueA = []

    # This scales as O(n*N) where n is number of moved files and N is number of files

    for path_oldA,path_newA in moved_Local.iteritems():
        # Is this path moved in remote
        if path_oldA not in moved_Remote:
            # No conflict. Either means it was not moved or it was deleted on A  
            fileBcurr = GetMatchingFile(curListB,path_oldA,'path') # Has not moved so use old path
        
            if fileBcurr is None: # Deleted on B. do nothing
                continue
            
            # Queue the move on remote and update fileB
            moveQueueB.append((path_oldA,path_newA))
            fileBcurr.path = path_newA

        else:
            # Moved on both B and A. A trumps the move
            # Queue the move from newB to newA. Update paths
            path_newB = moved_Remote[path_oldA]
            moveQueueB.append((path_newB,path_newA))
            fileBcurr = GetMatchingFile(curListB,path_newB,'path')
            fileBcurr.path = path_newA

    for path_oldB,path_newB in moved_Remote.iteritems():
        # Has the local path changed?
        if path_oldB not in moved_Local:
            # No conflict. Either was deleted or not moved
            fileAcurr = GetMatchingFile(curListA,path_oldB,'path')
        
            if fileAcurr is None: # no longer in A
                continue
        
            # If found this file needs to move. Update the path
            moveQueueA.append((path_oldB,path_newB))
            fileAcurr.path = path_newB
        else:
            # Local trumps remote. Do nothing
            pass
    
    return moveQueueB,moveQueueA

def B_ProcActQueue(action_queue,Machine=None,backupItems=None):
    global isBremote, B_host, B_pathToPBrsync,pathB

    if not isBremote:
        if backupItems is not None:
            perform_local_backup(backupItems,path=pathB)
            
        return ProcessActionQueue(pathB,action_queue,Machine=Machine)
    
    # Build a dictionary for the remote
    remoteDict = {'startPath':pathB,'action_queue':action_queue,'Machine':Machine}
    
    if backupItems is not None:
        remoteDict['backupList'] = backupItems
    
    tmpRemote = 'remoteB_' + randomString(8) + '.json'
    
    with open(tmpRemote,'w') as F:
        json.dump(remoteDict,F)
    
    # SCP the file
    pathB = StandardizeFolderPath(pathB)
    cmd = 'scp {0:s} {1:s}:{2:s}{0:s} > /dev/null 2>&1'.format(tmpRemote,B_host,pathB)
    os.system(cmd)
    os.remove(tmpRemote)
    
    # Build the remote commands
    
    remoteFile = '{:s}{:s}'.format(pathB,tmpRemote)
    cmd = 'ssh -T -q {:s} "{:s} API_runQueue {:s}"'.format(B_host,B_pathToPBrsync,remoteFile)
    
    tmpFile = randomString(10)  + '.dat'
    os.system(cmd + ' > ' + tmpFile)
    with open(tmpFile,'r') as F:
        remote_log = F.read()
        # Look for `'>>><<<>>><<<>>><<<>>><<<'` which is at the start of the file
        startIX = remote_log.find('>>><<<>>><<<>>><<<>>><<<')
        if startIX >= 0: # Found it
            remote_log = remote_log[startIX+24:] 
        remote_log = remote_log.splitlines()
        
    os.remove(tmpFile)
    
    for line in remote_log:
        addLog(line.replace('\n',''))
    
    
def ProcessActionQueue(startPath,action_queue,Machine=None):
    """
    Process the action queue. Form of 
        (PathOriginal,PathMoved) for a move or
        (PathOriginal,None)      for a delete
    """
    startPath = StandardizeFolderPath(startPath,check=False)
    
    for Original,Moved in action_queue:
        fullpathOrig = startPath + Original
        
        if Moved is not None:
            fullpathMoved = startPath + Moved
        
            MovedDir = os.path.dirname(fullpathMoved)
            if not os.path.exists(MovedDir):
                os.makedirs(MovedDir)
            
            entry = '{:s}: Moved {:s} --> {:s}'.format(Machine,Original,Moved)
            try:
                shutil.move(fullpathOrig,fullpathMoved)
                addLog(entry)
            except:
                addLog('ERROR IN: {:s}'.format(entry))
        else:
            entry = '{:s}: Deleted {:s} '.format(Machine,Original)
            try:
                if fullpathOrig.endswith('/'):
                    shutil.rmtree(fullpathOrig)
                else:
                    os.remove(fullpathOrig)
                addLog(entry)
            except:
                addLog('ERROR IN: {:s}'.format(entry))
        
def isFolderMod(file_list,oldListOTHER,folderStart):
    """
    Returns true if any file in a subfolder has been modified
    """
    
    for fileObj in file_list:
        if not fileObj.path.startswith(folderStart):
            continue
        
        if fileObj.modified:
            return True
        
        # is the file new?
        path = fileObj.path
        if GetMatchingFile(oldListOTHER,path,attribute='any') is None:
            # New:
            return True
    
    return False        
    
def GetMatchingFile(file_list,file_or_attribute,attribute='path'):
    """
    Return a file object from `file_list` that matches the `attribute` 
    of `file`
    
    Attributes:
        path    [default]
        inode
        any     (path + inode)
        (or anything else in the file object)
    
    Returns the file if found. Otherwise, returns None
    
    """
    
    # Not to self: This is O(N). I should try to improve it...
    
    if attribute.lower() == 'any':
        pmatch = GetMatchingFile(file_list,file_or_attribute,attribute='path' )
        imatch = GetMatchingFile(file_list,file_or_attribute,attribute='inode')
        if pmatch is not None:
            return pmatch
        if imatch is not None:
            return imatch
        return None
        
    if isfileObj(file_or_attribute):
        attribF = file_or_attribute.__dict__[attribute]
    else:
        attribF = file_or_attribute 
    
    for fileA in file_list:
        attribA = fileA.__dict__[attribute]
        if  attribA ==  attribF :
            return fileA
    
    return None

def logRsyncFinal(A2B,B2A):
    for log,dir in zip([A2B,B2A],['A >>> B','A <<< B']):
        addLog(dir)
        for item in log.split('\n'):
            if len(item)<2:
                continue
            
            
            action_path = [i.strip() for i in item.split(' ',1)]
            if len(action_path) != 2:
                addLog('Something Wrong with final action: {:s}'.format(item))
                continue
                
            action = action_path[0]
            path = action_path[1]    
            
            
            action = action.replace('<','>')
            
            if path.find('.JWempty') != -1: continue
            
            txt = ''
            
            if action.startswith('sent') or action.startswith('total'):
                addLog('  ' + item)
                continue
            
            if any([action.startswith(d) for d in ['receiving','building']]):
                continue

            if len(item.strip()) == 0: continue 
                
            if action.startswith('>'): txt +=          'Transfer  ' + path
            elif action.startswith('cd'): txt +=       'mkdir     ' + path
            elif action.startswith('.'): continue
            elif action.startswith('*deleting'): txt +='delete    ' + path
            else:  txt += action + ' ' + path
            
            addLog(txt,space=2)

def CompareRsyncResults(A2B,B2A,curListA,oldListA,curListB,oldListB):
    """
    Compare the rsync results
    
    Return
        queueA,queueB,excludeA2B,excludeB2A
    """
    
    global conflictProps
    conflictProps = []
    
    # For speed, build a dictionary of current file object by path
    fileDictA = {a.path:a for a in curListA}
    fileDictB = {b.path:b for b in curListB}
    
    
    ## Convert the actions into dictionaries
    
    rsyncDict_Files = {}
    rsyncDict_Folders = {}
    
    for b2a in B2A.split('\n'):
        if len(b2a) <2:
            continue
        if b2a.lower().startswith('cannot'):  # Edge case. Most likely gone now
            continue  
        
        try:  
            action,path = [a.strip() for a in b2a.split(' ',1)]
        except:
            print('Error Reading log:\n')
            print b2a
            sys.exit(2)
        
        if path.endswith('/'):        
            if path in rsyncDict_Folders:
                rsyncDict_Folders[path]['B2A'] = action
            else:
                rsyncDict_Folders[path] = {'B2A':action}
        else:
            if path in rsyncDict_Files:
                rsyncDict_Files[path]['B2A'] = action
            else:
                rsyncDict_Files[path] = {'B2A':action}
                
    for a2b in A2B.split('\n'):
        if len(a2b) <2:
            continue              
        
        if a2b.lower().startswith('cannot'):
            continue
        
        try:
            action,path = [a.strip() for a in a2b.split(' ',1)]      
        except:
            print('Error Reading log:\n')
            print b2a
            sys.exit(2)
        
        
        if path.endswith('/'):        
            if path in rsyncDict_Folders:
                rsyncDict_Folders[path]['A2B'] = action
            else:
                rsyncDict_Folders[path] = {'A2B':action}
        else:
            if path in rsyncDict_Files:
                rsyncDict_Files[path]['A2B'] = action
            else:
                rsyncDict_Files[path] = {'A2B':action}
    
    queueA = [] 
    queueB = []
    
    excludeA2B = []
    excludeB2A = []
    
    # Process Folders first
    skipFolderPaths = []
    for folderPath in sorted(rsyncDict_Folders.keys()):
        # Since file moves have been accounted for, all folder actions are 
        # delete on one end and create on another. Folders themselve cannot 
        # conflict
        
        if any([folderPath.startswith(d) for d in skipFolderPaths]):
            continue
        
        actions = rsyncDict_Folders[folderPath]
        a2b = b2a = ''
        if 'A2B' in actions:
            a2b = actions['A2B']
        if 'B2A' in actions:
            b2a = actions['B2A']

        # Non-file modifications
        if a2b.startswith('.') and b2a.startswith('.'):
            continue
            
        # A wants to delete, B wants to create/transfer:
        if a2b.startswith('*del') and b2a.startswith('cd+'):
            # has it been modified on B?
            if isFolderMod(curListB,oldListA,folderPath):
                # do nothing. Allow this action
                pass
            else: # Delete it on B
                queueB.append((folderPath,None))
                skipFolderPaths.append(folderPath) # skip it's children
            continue
            
        # A wants to create/transfer, B wants to delete

        if a2b.startswith('cd+') and b2a.startswith('*del'):
            if isFolderMod(curListA,oldListB,folderPath):
                # do nothing. Allow this action
                pass
            else: # Delete it on A
                queueA.append((folderPath,None))
                skipFolderPaths.append(folderPath) # skip it's children
            continue
        
        # We should only get here if there is an error
        print('ERROR Dir Comp: {:s}. A2B: {:s} B2A:{:s}'.format(folderPath,a2b,b2a))

    # Process files
    for filePath in sorted(rsyncDict_Files.keys()):
        
        if any([filePath.startswith(d) for d in skipFolderPaths]):
            continue
        
        if filePath.endswith('.JWempty'):
            continue
        
        if any([filePath.endswith(d) for d in excludeNames]):
            continue
        
        if any([filePath==d for d in excludePaths]):
            continue
        
        actions = rsyncDict_Files[filePath]
        a2b = b2a = None
        if 'A2B' in actions:
            a2b = actions['A2B']
        if 'B2A' in actions:
            b2a = actions['B2A']

        # In THEORY there should never be a None item since any difference will
        # require an overwrite. But, I *think* this is a bug. Log it and then move on
        if a2b is None:
            addLog('WARNING: no matching A >>> B action on {:s}'.format(filePath),space=5)
            addLog('This *may* be an rsync bug',space=8)
            continue
        if b2a is None:
            addLog('WARNING: no matching A <<< B action on {:s}'.format(filePath),space=5)
            addLog('This *may* be an rsync bug',space=8)
            continue
            
        # Replace all `<` with `>` since I do not care about the direction
        a2b = a2b.replace('<','>')
        b2a = b2a.replace('<','>')

        
        # conflict types.

        # 0 conflicting properties. Ignore but store for conflicting props
        if a2b.startswith('.') and b2a.startswith('.'): 
            excludeB2A.append(filePath)
            excludeA2B.append(filePath)
            conflictProps.append(filePath)
        
        # 1: A and B both show a transfer
        if a2b.startswith('>') and b2a.startswith('>'):
 
            try:
                fileA = fileDictA[filePath]
                fileB = fileDictB[filePath]
            except KeyError:
                addLog('Error with file: {:s}'.format(filePath))
                addLog('skipping...')
                continue
                
            
            if fileA.modified and not fileB.modified:
                # Exclude from B2A
                excludeB2A.append(filePath)
                continue
                
            if not fileA.modified and fileB.modified:
                # Exclude in A2B
                excludeA2B.append(filePath)
                continue
            
            if (fileA.modified == fileB.modified):
                addLog('CONFLICT: {:s}'.format(filePath))
                if fileA.modified:
                    addLog('  Both Modified')
                else:
                    addLog('  Both Un-Modified (Edge Case?)')
                if conflictMode == 'newer':
                    if fileA.mtime >= fileB.mtime: # A is newer
                        excludeB2A.append(filePath)
                        addLog('    Keep Newer (A)')
                    else:
                        excludeA2B.append(filePath)
                        addLog('    Keep Newer (B)')
                elif conflictMode == 'a':
                    excludeB2A.append(filePath)
                    addLog('    Always Keep A')
                elif conflictMode == 'b':
                    excludeA2B.append(filePath)
                    addLog('    Always Keep B')
                else:
                    queueA.append((filePath,filePath+'.'+Aname))
                    queueB.append((filePath,filePath+'.'+Bname))
                    addLog('    Keep Both (and rename)')
                continue
            continue
        
        # 2 A shows a delete, B shows a transfer.
        if a2b.startswith('*del') and b2a.startswith('>'):
            
            # Is it a new file in B (regardless of age)
            if GetMatchingFile(oldListA,filePath,attribute='any') is None:
                # New in B Ignore for transfer. This also accounts for when an older file is moved into the directory
                # addLog('NEW B: {:s}'.format(filePath))
                continue # Do not move on
            
            fileB = fileDictB[filePath]
            
            if not fileB.modified: # Not modified and not new (new checked above)
                queueB.append((filePath,None))
                continue
            
            addLog('CONFLICT: File deleted on A but modified on B: {:s}'.format(filePath))
            # Nothing needs to happen here since we won't be using the --delete flag        


        # 3 A shows a transfer, B shows a delete
        if a2b.startswith('>') and b2a.startswith('*del'):
            
            # Is it a new file in A(regardless of age)
            if GetMatchingFile(oldListB,filePath,attribute='any') is None:   
                # New in A Ignore for transfer. This also accounts for when an older file is moved into the directory
                # addLog('NEW A: {:s}'.format(filePath))
                continue # Do not move on
            
            fileA = fileDictA[filePath]
            if not fileA.modified: # Not modified and not new (new checked above)
                queueA.append((filePath,None))
                continue
            
            addLog('CONFLICT: File deleted on B but modified on A: {:s}'.format(filePath))
    return queueA,queueB,excludeA2B,excludeB2A

def perform_local_backup(items,path=None):
    global tmpLogSpace
    
    if path is None:
        path = pathA
    
    backDir = path +'.PBrsync/file_backups/' + datetime.now().strftime('%Y-%m-%d_%H%M%S')
    backDir =  StandardizeFolderPath(backDir)
    
    
    tmpLogSpace = 0
    addLog(' ')
    addLog('Backuping up soon to be modified files')
    if items is None or len(items)==0:
        addLog('    * None * ')
        return
    
    addLog('  REMINDER: files are *only* backed up if they will be overwritten')
    addLog('  or deleted. Not if they are or will be moved.')
    addLog('  Directory: {:s}'.format(backDir))
    addLog('  Files: ')
    tmpLogSpace = 4
    
    if items is None or len(items)==0:
        addLog('    * None * ')
        return
    
    os.makedirs(backDir)
    
    for item in items:
        if item.endswith('.JWempty'): continue
        
        if item.endswith('/'):
            shutil.copytree(path + item, backDir + item)
        else:
            dirTmp = os.path.dirname(backDir + item)
            if not os.path.exists(dirTmp):
                os.makedirs(dirTmp)
                
            shutil.copy2(path + item, backDir + item)
        addLog(' * ' + item)
    
    if len(items) == 0:
        addLog('* None *')
    addLog(' ')    
    
def snapshot(path='.',force=False,excludes=[]):
    """
    Perform a snapshot
    """
    # Must be an absolute path
    path = StandardizeFolderPath(os.path.abspath(path))
    
    global RsyncFlags
    
    # See if the path is a PBrsync directory
    if os.path.exists(path + '.PBrsync/config'):
        parseInput(path)
        if not allow_snap:
            print('Snapshots not allowed')
            sys.exit(2)
    elif force:
        global pathA
        pathA = path
    else:
        print('Not a PBrsync directory')
        sys.exit(2)
        
    
    RsyncFlags += ['-H','-a','--exclude','.PBrsync'] 
    RsyncFlags += ['--stats'] # Disallowed flag so set *after* parsing input
    
    for item in excludes:
        RsyncFlags += ['--exclude',item]
    
    addLog('#'*60)
    addLog('# PBrsync -- Python-wrapper for Bi-directional rsync')
    addLog('#')
    addLog('#      >>>>> Use at your own risk!!! <<<<<')
    addLog('#')    
    addLog(' ')
    addLog('Date: {:s} ({:s} Unix Time)'.format(datetime.now().strftime('%Y-%m-%d_%H%M%S'),str(time.time())))
    addLog(' ')
    addLog(' Snapshot Mode: ')
    addLog('   Path: {:s}'.format(pathA))
    addLog(' ')
    addLog('-'*60)
    addLog(' ')
    
    snapDestDir = StandardizeFolderPath(path + '.PBrsync/snapshots/')
    snapDest = snapDestDir + datetime.now().strftime('%Y-%m-%d_%H%M%S')
    snapDest = StandardizeFolderPath(snapDest)
    
    if not os.path.exists(snapDestDir):
        os.makedirs(snapDestDir) # First one, make directory:
        
    oldSnaps = os.listdir(snapDestDir)
    
    
    if len(oldSnaps) == 0:
        # This is the first snap shot. Do a full copy
        output = subprocess.check_output(['rsync']+RsyncFlags + [path,snapDest],stderr=DEVNULL)
        addLog('Initial snapshot. Note this is full copy')
        addLog('but future copies will only be changes')
    else:    
        # Get the last snapshot
        linkDir = snapDestDir + sorted(oldSnaps)[-1] # Newest
    
        RsyncFlags += ['--link-dest={:s}'.format(linkDir)]
        output = subprocess.check_output(['rsync']+RsyncFlags + [path,snapDest],stderr=DEVNULL)
        
        addLog(' Snapshot generated in {:s}'.format(snapDest))
        addLog('  Used {:s} to link unchaged files'.format(linkDir))
    
    addLog(' ')
    addLog('-'*60)
    addLog(' ')
    addLog('Rsync Summary (stats):')
    for line in output.split('\n'):
        addLog(line,space=4,flush=False)
    addLog(' ')
    addLog('Saved Log in {:s}'.format(logFile.name),flush=True)
    logFile.close()
    
def remoteSnap(path='.',excludes=[]):
    path = StandardizeFolderPath(os.path.abspath(path))
    
    parseInput(path)

    addLog('#'*60)
    addLog('# PBrsync -- Python-wrapper for Bi-directional rsync')
    addLog('#')
    addLog('#      >>>>> Use at your own risk!!! <<<<<')
    addLog('#')    
    addLog(' ')
    addLog('Date: {:s} ({:s} Unix Time)'.format(datetime.now().strftime('%Y-%m-%d_%H%M%S'),str(time.time())))
    addLog(' ')
    addLog(' Remote Snapshot Mode: ')
    addLog('   User: {:s}'.format(B_host))
    addLog('   Path: {:s}'.format(pathB))
    addLog(' ')
    addLog('-'*60)
    addLog(' ')
    
    excludes += excludeDirs + excludePaths + excludeNames
    
    excludeTXT = ''.join([' --exclude {:s} '.format(a) for a in excludes]).replace('  ',' ')
    
    cmd = 'ssh -T -q {:s} "{:s} snapshot {:s} --force {:s}"'.format(B_host,B_pathToPBrsync,excludeTXT,pathB)

    addLog(' Calling:')
    addLog('  `{:s}`'.format(cmd))
    
    tmpFile = randomString(10)
    os.system(cmd + ' > ' + tmpFile)
    with open(tmpFile,'r') as F:
        remote_log = F.readlines()
    os.remove(tmpFile)
    
    addLog(' ')
    addLog('-'*60)
    addLog('Remote Log:')
    addLog(' ')
    
    for line in remote_log:
        addLog('  > ' + line.strip(),flush=False)
    
    addLog(' ')
    addLog('-'*60)
    addLog('Saved Log in {:s}'.format(logFile.name),flush=True)
    logFile.close()
def byteify(input):
    """
    Recursivly convert keys to strings
    From : http://stackoverflow.com/a/13105359
    with minor changes
    """
        
    # I do not think this is needed but will keep it around for now just in case
    return input
    
    if isinstance(input, dict):
        retDict = {}
        for key,value in input.iteritems():
            retDict[byteify(key)] = byteify(value)
        return retDict
    elif isinstance(input, list):
        return [byteify(element) for element in input]
    elif isinstance(input, unicode):
        return input.encode('utf-8')
    else:
        return input

def randomString(N=5):
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10)) 

def init(path='.',force=False):
    global pathA
    path = StandardizeFolderPath(path)
    pathA = path
    
    if os.path.exists(path + '.PBrsync'):
        if not force:
            print("Already a PBrsync directory.\nAre you sure you want to overwrite it? Y/[N]")
            input = raw_input('')
            if not input.lower().startswith('y'):
                print('exit')
                sys.exit()
    else:
        os.makedirs(path + '.PBrsync')
    
    addLog('Created PBrsync directory')
    reset_configfile(path=path,force=force)
    
    addLog('-='*30)
    addLog(' ')
    addLog(' Initialized new PBrsync Directory. You must first')
    addLog('    * Modify the config file (self-commented)')
    addLog('       {:s}'.format(path + '.PBrsync/config'))
    addLog('    * First perform a `reset-files`, `push`, or `pull`, opperaton')
    addLog('=-'*30)
    
def reset_configfile(path='.',force=False):
    global pathA
    path = StandardizeFolderPath(path)
    pathA = path
    
    if not os.path.exists(path + '.PBrsync'):
        print('Not a PBrsync directory')
        sys.exit(2)
    
    if os.path.exists(path + '.PBrsync/config'):
        if not force:
            addLog("\nConfig already exists.\nAre you sure you want to overwrite it? Y/[N]")
            input = raw_input('')
            if not input.lower().startswith('y'):
                print('exit')
                sys.exit()

        newName = path + '.PBrsync/config-' + datetime.now().strftime('%Y-%m-%d_%H%M%S') 
        shutil.move(path + '.PBrsync/config',newName)
        addLog('Saved old file as {:s}'.format(newName))
    
    fullpath = StandardizeFolderPath(os.getcwd()) + path
    
    configTXT = """\
#################################################################
######################### PBrsync Config ########################
#################################################################
# 
# For both remote and local, specify
#   path            :   Full, absolute path to the files on 
#                       respective platform (local path will 
#                       auto-fill)
#   name            :   Name for the machine
#   
# Additionally for a real remote machine, specify
#   host            :   user@host.name
#   PBrsync         :   Path the the PBrsync.py file
#   
#   If those are not specified, it assumes a local "remote" 
#   machine 
# 
# Exclusions -  Sepecify individually
#   dir             :   Full (relative) path to exclude 
#                       directories
#   paths           :   Full (relative) path to exclude file
#   names           :   Exclude any file with this name
# 
#   All exlusions are added to the rsync --exclude
#
# Backup Settings - 
#   snapshots       :   Allow snapshots in this directory
#   localbackup     :   Backup all files that are to be 
#                       overwritten or deleted. Does not back up 
#                       files to be moved. Only applies to `sync`
#   remotebackup    :   Backup all remote files before 
#                       overwritten or deleted. Only applies to 
#                       sync
# Other Settings - 
#   RsyncFlags      :   Additional rsync flags. Some examples:
#                           --checksum      [default there]. Use 
#                                           checksums for rsync 
#                           -H,--hard-links Maintain Hardlinks
#                           --partial       [Default here]. Keep
#                                           partial transfers
#   check_ctime     :   If True also checks the creation time for
#                       moved files (in addition to inode number)
#   conflictMode    :   How to hanle file content conflicts (move
#                       conflicts are handled differently)
#                [default]  both  - Rename with tag and keep both
#                           newer - Keep the newest version
#                           A     - Always keep the local (A)
#                           B     - Always keep the remote (b)
#
#################################################################

[local]
path = {pathA:s}
name = machineA

[remote]
name = machineB
path = /full/path/to/remote/dir/

host = user@host
PBrsync = /full/path/to/PBrsync.py

[backups]
# These are also the defaults if you remove them:
snapshots = True
localbackup = True
remotebackup = True

[other]
RsyncFlags = --checksum
RsyncFlags = --partial
conflictMode = both 
# conflictMode = newer
# conflictMode = A
# conflictMode = B



# These are also the defaults if you remove them:
check_ctime = False


[exclusions]
# Remember to specify only one item per parameter

## Example
# dir = exlcude_dir1
# dir = exclude_dir2
# name = ignore_me.txt
# path = ignore/specific/path.txt
# path = ignore/another/path.txt
""".format(**{'pathA':fullpath})
    with open(path + '.PBrsync/config','w') as F:
        F.write(configTXT)
    print('Saved config file to: {:s}.PBrsync/config'.format(path))
    
def resetfiles(path='.',force=False):
    global pathA
    path = StandardizeFolderPath(path)
    pathA = path
    
    start()
    
    addLog('Resetting file tracking')
    
    
    
    if any([a in os.listdir(pathA + '.PBrsync') for a in ['local_old.list','remote_old.list']]):
        if not force:
            addLog("\nState file(s) already exists.\nAre you sure you want to overwrite? Y/[N]")
            input = raw_input('')
            if not input.lower().startswith('y'):
                print('exit')
                sys.exit()

    addLog('='*60)
    addLog(' Files have been reset. It is now STRONGLY reccomended that you')
    addLog(' perform a sync')
    addLog('=-'*30)
    
    cleanup()
    
    # Overwrite the file times
    with open(pathA+'.PBrsync/lastrun','w') as F:
        F.write('1.01')
    
      

def usage(cmd=None):
    usageFull = """\
    
    PBrsync -- A python wrapper for rsync providing bi-directional sync
              with smart (inoded and create-time) base.
    
    Usage:
        PBrsync.py <command> [options]
    
    Main Commands:
      This is not all commands since some are for remote "API-like" calls  
        
        help        : Display this message (use `<command> -h` for specific)
        init        : Initialize the path for PBrsync (then use an
                      additional command noted below)  
        snapshot    : Perform a local (or attemp remote with `--remote`) 
                      snapshot. Only if configured to allow
        sync        : Perform the sync (use `--silent` for cron. See `--help` 
                      for more)
                      
    Additional Commands:
      To be used with caution. Note that push/pull do not include backups.
    
        pull        : Clobber local files with remote (no delete by default)
        push        : Clobber remote files with local (no delete by default)
        resetconfig : Reset's the config
        resetfiles  : Reset the stored file paths to the current state    
    """
    
    usageSync = """\
    Usage:
        PBrsync.py sync [flags] [path]
    
    Perform sync actions
    
    Flags:
        -h,--help   : Print this help
        --silent    :   Do not display anything to the terminal
    Options:
        path        :   ['.'] Path to sync directory        
    """
    
    usagePullPush = """\
    Pull/Pull (and clobber) local (Pull) or remote (Push) with the other
    
    Usage:
        PBrsync.py pull [flags] [path]
        PBrsync.py push [flags] [path]
    
    Flags:
        -d,--delete : Sets delete flag on rsync
        -h,--help   : Print this help
        --silent    :   Do not display anything to the terminal
    
    Options:
        path        :   ['.'] Path to sync directory  
    """
    usage_resetconfig ="""
    
    Usage:
        PBrsync.py resetconfig <options> [path]
    
    Options: (Use a separate arg for each  directory, path, or name)
        -f,--foce       :   Force it w/o promting 
        -h,--help       :   Display Help
    
    Arguments:
        path            :   ['.'] Path to sync directory  
        
    """
    usage_resetfiles ="""
    
    Reset files to the current state. Will remove ability to track moves
    
    Usage:
        PBrsync.py resetfiles <options> [path]
    
    Options: (Use a separate arg for each  directory, path, or name)
        -f,--foce       :   Force it w/o promting 
        -h,--help       :   Display Help
    
    Arguments:
        path            :   ['.'] Path to sync directory  
        
    """
    usage_init ="""
    Initialize the directory
    
    Usage:
        PBrsync.py init  [flags] [path]
     
     Flags:
        -h,--help   : Print this help
          
    Arguments:
        path        :   ['.'] Path to sync directory  
        
    """
    
    usage_snapshot = """\
    
    Usage:
        PBrsync.py snapshot <options> [path]
    
    Note:
        The initial snapshot is a full copy (and will use space accordingly).
        After that though, snapshots *look* like the full system but are 
        hard-links when possible.
        
        Also, note that snapshots are stored in the `.PBrsync` directory so if
        that directory is deleted, they are too.
    
    Options:
        --exclude   :   Set rsync excludes
        --force     :   Force the snapshot even if not a PBrsync directory
                        Will **NOT** overrule a config that dissallows 
                        snapshots. See note below
        -h,--help   :   Display this message
        -R,--remote :   Attempt to perform a snapshot of the remote server.
                        If the remote server is configured for PBrsync, it will
                        follow the config  `allow_snapshot` setting. Otherwise,
                        it will proceed. See note below
        --silent    :   Silent Mode
    
    Arguments:
        path        :   ['.'] Path to sync directory 
        
    Note that doing a snapshot on a non-PBrsync directory (with `--force`) or,
    if done with `--remote`) it will not use any configured exclusions unless 
    they are in the local config file
    
        
    """
    
    usageAPI_listFiles = """\
    
    Usage:
        PBrsync.py API_listFiles <options> path
    
    Options: (Use a separate arg for each  directory, path, or name)
        -c              :   Set to add a temp file for an empty directory
        --excludeDir    :   Directory to be excluded.
        --excludePath   :   Specific (relative) path to exclude
        --excludeName   :   Any file with this name
        -d              :   Set to delete the temp files
        -h,--help       :   Display Help
    
    Arguments:
        path            :   Path to list
        
    """
    
    usageAPI_runQueue = """\
    
    PBrsync.py API_runQueue <options> path_to_queueDict
    
    Options:
        -h,--help       :   Display Help
    
    Arguments:
        path_to_queueDict   :   Path to a JSON dictionary with:
                                `startPath`,`action_queue`,`Machine`
    
    """
           
    if cmd is None:
        cmd = 'main'
    
    if cmd in ['main']:
        print(usageFull)
    if cmd in ['init']:
        print(usage_init)
    if cmd in ['pull','push','pushpull','pullpush']:
        print(usagePullPush)
    if cmd in ['resetconfig']:
        print(usage_resetconfig)
    if cmd in ['resetfiles']:
        print(usage_resetfiles)
    if cmd in ['snapshot']:
        print(usage_snapshot)
    if cmd in ['sync']:
        print(usageSync)
    if cmd in ['API_listFiles']:
        print(usageAPI_listFiles)
    if cmd in ['API_runQueue']:
        print(usageAPI_runQueue)
    
if __name__ =='__main__':
    
    try:
        mode = sys.argv[1]
    except IndexError:
        usage()
        sys.exit(2)
    argsIN = sys.argv[2:]
    #### Heuristics to try to get at a default mode
    # Edge case not considered is if there is a help flag in addition to other flags
    # Possible Input examples
    #   ./Pbrsync sync folder     (a) -- Default
    #   ./Pbrsync sync -f folder  (b) -- Default
    #   ./Pbrsync folder          (c)
    #   ./Pbrsync -f folder       (d)
    #   ./Pbrsync -h (or --help)  (e)
    #   ./Pbrsync help            (f)
    if  not ( mode == 'help' or mode == '--help' or mode == '-h' ): #(e,f)
        if mode.startswith('-') : # Case (d)
            argsIN = [mode] + argsIN
            mode = 'sync'
        if len(argsIN) == 0: # case (c)
            argsIN = [mode]
            mode = 'sync'
    
    
    if mode in ['help','-h','--help']:
        usage()
        sys.exit(2)
    elif mode == 'sync':
        try:
            opts, args = getopt.getopt(argsIN, "h", ["help","silent"])
        except getopt.GetoptError as err:
            print str(err) #print error
            print "\n Printing Help:\n"
            usage('sync')
            sys.exit(2)        
        
        path = '.'
        if len(args) >0:
            path = args[0]
        
        path = StandardizeFolderPath(path)
        for o,a in opts:
            if o in ("-h", "--help"):
                usage('sync')
                sys.exit()
            if o in ['--silent']:
                silent=True      
     
        sync(path)
    
    elif mode in ['pull','push']:
        try:
            opts, args = getopt.getopt(argsIN, "hd", ["help","silent","delete"])
        except getopt.GetoptError as err:
            print str(err) #print error
            print "\n Printing Help:\n"
            usage('pull')
            sys.exit(2)        
        
        delete = False
        path = '.'
        if len(args) >0:
            path = args[0]
        path = StandardizeFolderPath(path)
        for o,a in opts:
            if o in ("-h", "--help"):
                usage('pull')
                sys.exit()
            if o in ['--silent']:
                silent=True
            if o in ['-d','--delete']:
                delete = True
                 
        pushpull(path,mode,delete=delete)
    elif mode == 'resetconfig':
        try:
            opts, args = getopt.getopt(argsIN, "hf", ["help","force"])
        except getopt.GetoptError as err:
            print str(err) #print error
            print "\n Printing Help:\n"
            usage('resetconfig')
            sys.exit(2)        
        
        force = False
        path = '.'
        if len(args) >0:
            path = args[0]
        path = StandardizeFolderPath(path)
        for o,a in opts:
            if o in ("-h", "--help"):
                usage('resetconfig')
                sys.exit()
            if o in ['--force','-f']:
                force = True
        
        reset_configfile(path,force=force)
    elif mode == 'init':
        try:
            opts, args = getopt.getopt(argsIN, "hf", ["help","force"])
        except getopt.GetoptError as err:
            print str(err) #print error
            print "\n Printing Help:\n"
            usage('init')
            sys.exit(2)        
        
        force = False
        path = '.'
        if len(args) >0:
            path = args[0]
        path = StandardizeFolderPath(path)
        for o,a in opts:
            if o in ("-h", "--help"):
                usage('init')
                sys.exit()
            if o in ['--force','-f']:
                force = True
        
        init(path,force=force)
    elif mode == 'snapshot':
        try:
            opts, args = getopt.getopt(argsIN, "hR", ["help","remote","silent","force","exclude="])
        except getopt.GetoptError as err:
            print str(err) #print error
            print "\n Printing Help:\n"
            usage('snapshot')
            sys.exit(2)        
        
        path = '.'
        if len(args) >0:
            path = args[0]
        path = StandardizeFolderPath(path)
        
        performRemote = False
        force = False       
        excludes = []
        
        for o,a in opts:
            if o in ("-h", "--help"):
                usage('snapshot')
                sys.exit()
            if o in ['--remote','-R']:
                performRemote = True # Set if first to get all of the options
            if o in ['--silent']:
                silent=True 
            if o in ['--force']:
                force=True
            if o in ['--exclude']:
                excludes.append(a)
                
        
        if performRemote:
            remoteSnap(path,excludes=excludes)
            sys.exit()        
        
        snapshot(path,force=force,excludes=excludes)       
    elif mode == 'resetfiles':
        try:
            opts, args = getopt.getopt(argsIN, "hf", ["help","force"])
        except getopt.GetoptError as err:
            print str(err) #print error
            print "\n Printing Help:\n"
            usage('resetfiles')
            sys.exit(2)        
        
        force = False
        path = '.'
        if len(args) >0:
            path = args[0]
        path = StandardizeFolderPath(path)
        
        for o,a in opts:
            if o in ("-h", "--help"):
                usage('resetfiles')
                sys.exit()
            if o in ['--force','-f']:
                force = True
        
        resetfiles(path,force=force)        
    elif mode == 'API_listFiles':
        silent = True
        try:
            opts, args = getopt.getopt(argsIN, "hcd", ["help","excludeDir=","excludePath=","excludeName="])
        except getopt.GetoptError as err:
            print str(err) #print error
            print "\n Printing Help:\n"
            usage('API_listFiles')
            sys.exit(2)
        
        # Defaults
        empty = None 
        # Parse
        for o,a in opts:
            if o in ("-h", "--help"):
                usage('API_listFiles')
                sys.exit()
            if o in ['--excludeDir']:
                if a not in excludeDirs:
                    excludeDirs.append(a)
            if o in ['--excludePath']:
                if a not in excludePaths:
                    excludePaths.append(a)
            if o in ['--excludeName']:
                if a not in excludeNames:
                    excludeNames.append(a)
            if o in ['-c']:
                if empty is not None:
                    print('WARNING: overwriting `empty` command')
                empty='create'
            if o in ['-d']:
                if empty is not None:
                    print('WARNING: overwriting `empty` command')
                empty='delete'
            
        try:
            path = StandardizeFolderPath(args[0],check=False)
        except:
            print("\nMust specify a path")
            usage('API_listFiles')
            sys.exit(2)
        global pathA
        pathA = path
        
        list = FileInfoList(path,empty=empty)
        print '>>><<<>>><<<>>><<<>>><<<' # Random stuff to know when to start
        print list            
    elif mode == 'API_runQueue':
        
        tmpLogSpace = 0
        silent = True
        
        try:
            opts, args = getopt.getopt(argsIN, "h", ["help"])
        except getopt.GetoptError as err:
            print str(err) #print error
            print "\n Printing Help:\n"
            usage('API_listFiles')
            sys.exit(2)
        for o,a in opts:
            if o in ("-h", "--help"):
                usage('API_runQueue')
                sys.exit() 
        
        try:
            path = args[0]
        except:
            print("\nMust specify a path")
            usage('API_runQueue')
            sys.exit(2)
        
        with open(path,'r') as F:
            remoteDict = byteify(json.load(F))
        os.remove(path)
        
        pathA = remoteDict['startPath']
        
        if 'backupList' in remoteDict:
            perform_local_backup(remoteDict['backupList'],path=pathA)
        
        ProcessActionQueue(remoteDict['startPath'],remoteDict['action_queue'],Machine=remoteDict['Machine'])
        
        print '>>><<<>>><<<>>><<<>>><<<' # Random stuff to know when to start
        print '\n'.join(log)
            
         
    else:
        print('Unrecognized Mode')
        usage()
        sys.exit(2)        















































