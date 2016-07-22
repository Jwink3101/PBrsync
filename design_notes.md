# Design Notes

These are roughly how the code works. The code itself if fairly well documented so see that for more.

## Sync Operations

* The local and remote file tree is parsed generating a list of all files including their modification date, creation time, and inode number
    * See  Remote Operations for how it's done on the remote
    * If an empty folder is encountered, a temp file is created
* File moves are detected (based on inode numbers and optionally, creation time)
    * For both the local and remote, a list of all moved files is generated
    * Local moves are checked against the remote
        * If not moved on the remote, check if it has been deleted. If not, queue the move on the remote
        * If it has been moved on the remote, the local move takes preference
            * If it was moved the same, it will generate a move action that does nothing
    * Remote moves are checked against local
        * if not moved on local, check for deleted. If not deleted, queue the move locally
        * Conflicting moves are already addressed above
* Perform the moves locally and remotely
    * See remote operations
* Rsync both ways are run with `--dry-run` and with `--delete`. The intended actions are compared:
    * Note:
        * The final Rsync operation will not be with `--delete`
        * All opperations *should* be on both sides 
        * Only possible folder action is delete
    * Folder Deletions are compared (first A on B then B on A)
        * If there are no modified files in the to-be-deleted folder, the deletions is queued
    * File actions are compared:
        * If the action is just properties and not content, it is ignored
        * If both show a transfer:
            * If the file on A is modified but not on B, if it added to a list of files to ignore on the B side
                * We do not delete so that rsync can use it's delta-transfers
            * If file B has been modified but file A has not it is added to a list of files to ignore on the A side
                * We do not delete so that rsync can use it's delta-transfers
            * If both or neither have been modified (latter being a strange egde case), they follow the  `conflict_mode` and a note is made in the log.
        * If A wants to delete and B wants to transfer
            * If the file is new on B do nothing (allow transer)
            * If the file is not modified on B, queue the delete
            * If the fils has been modified on B, do nothing and allow the transfer
                * Modified file trumps deletions
        * If B wants to delete but A wants to transfer
            * If the file is new on A, do nothing (allow transfer)
            * If the file is not modified on A, queue the delete on A
            * if the file has been modified on A, do nothing and allow the transfer
                * Modified file trumps deletions
        * In the above, a file being new is checked off the *other* file list. The two "old"/initial lists *should* be identical but this is to handle an edge case.
* The list of to-be-deleted files along with to be ignored files constitutes a list of all files to be modified.
    * Backup the files locally and tell the remote to back up
* Perform local backups (if applicable) and moves/deletions
* Perform remote backups (if applicable) and moves/deletions
* Two rsync operations are now done to push and pull
    * No `--delete` flag
    * A list of files to exclude is written and passed to rsync
* The *new* local and remote file listing is requested and saved


## Remote Opperations

The config requires the user to specify the path to the `PBrsync.py` file. All told, there are 10 remote connections (all from local to host)

* Current file listing (1)
* Apply moves
    * Upload JSON instruction (2)
    * Send command to read and perform actions (3)
* dry-run Rsync both ways
    * Local to remote (4)
    * Remote to local (5)
* Apply moves and deletions 
    * Upload JSON instruction (6)
    * Send command to read and perform actions (7)    
* Final Rsync both ways
    * Local to remote (8)
    * Remote to local (9)
* Ask for updated listing (10)

I am looking into using a persistant SSH tunnel to save a lot of time

### File Listing:

File listing is done by a simple remote call of the form:

    ssh -T <user@hostname> "<path/to/PBrsync.py> API_listFiles <options> path/to/B

where the `API_listFiles` will read the options (including exclusions specified locally) and will return the file listing

### Remote Moves

This is a bit more complex. A JSON file is written locally containing the path and the actions. Also, if a backup is to be done, a list of files to back up is also sent

Then, that file is uploaded with `scp` to the remote directory and an SSH call as follows if performed 
    
    ssh -T <user@hostname> "<path/to/PBrsync.py> API_runQueue path/to/uploaded_file

Now `API_runQueue` will read the JSON file, delete it, and perform the actions (again, will only do a backup if files are specified for backup)        
  
### Snapshots

Snapshots are done by a remote call of the following form

    ssh -T <user@hostname> "<path/to/PBrsync.py> snapshot --force /path/to/B
    
where the `--force` option forced the snapshot to happen even if it is not a PBrsync directory. Note that, unless it is a PBrsync directory with a config file, there is no way to add exclusions (may be work initializing for the config files.....)      
