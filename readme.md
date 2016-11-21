# `PBrsync` --  Python Wrapper for Bidirectional `rsync` 

**>>>>> Use at your own risk!!! <<<<<**

This tool came out of a need for bi-directional synchronization that works on a [fairly] stock Mac OS or Linux set up.

There are other tools like it and for many, they are probably better. This fit a special niche for me. See below for more details


## Usage:

### `Help` Info

The main file has the following `--help` information:

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
                      
**All commands also have a `--help` flag** so see them for individual usage

### Remote Setup:

None really. Just have a folder ready. Your remote can also be initialized with PBrsync for *a different* remote. Or you can initialize to get the config file for specifying settings.

On remote:
    
    $ # install PBrsync.py somewhere
    $ mkdir /path/to/remote/folder/

### Local set up.

First, it is assumed that you have `PBrsync.py` with installed somewhere or in your path. For this, I will assume it is in your path

Assuming you do not all ready have a directory:

    $ mkdir /path/to/local/folder/

Initialize (again, assume `PBrsync` is in your path)
    
    $ ./PBrsync.py init /path/to/local/folder/

Now you must:

* Configure the file in `/path/to/local/folder/.PBrsync/config`
    * The local directory is auto-filled
    * See the config file for documentation
* Perform either `resetfiles`, `push`, or `pull`
    * `resetfiles` will reset file tracking of moves, etc [**Safest**]
        * Will tell PBrsync that all files are now new.
        * *Highly reccomended* that you immediately do a sync
    * `push` or `pull`
        * `push` will mirror the local directory to the remote 
        * `pull` will mirror the remote directory to the local
        * Both will not delete files inless called with `--delete`
        * There are *no backups* with this

Assume `resetfiles`:
    
    $ PBrsync.py resetfiles /path/to/local/folder/

Now you're all set:

    $ PBrsync.py sync /path/to/local/folder/

**WARNING / REMINDER**: If you have a lot of files already you can set to keep the newest on conflicts but keep a backup, do a sync, and then reset to keep both on conflict.

Also, if you have disjoint directories based on names, you can do a push or a pull but add `--fuzzy` to the config file
    
### Configuration

The automatic `config` file has instructions. They are also reproduced below:

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

## How it Works:

`PBrsync` is a python-wrapper around multiple rsync calls. By storing a snapshot of the past file-system and tracking inode numbers (and optionally, creation time) moves are detected and applied. For more detials, read the design notes.

There is no interactivity. Based on the (self commented) config settings, you can either resolve conflicts by keeping the newest (and hopefully having backups on), keeping both, or always keeping either local or remote. If you don't have both local and remote backups on with the setting to only keep the newest, it will warn you and then wait 3 seconds


For types of conflicts and how they are resolved, see [design notes](design_notes.md)

## Snapshots and Backups

If set in the config file, all files and folders that would be overwritten or deleted can be backed up in `.PBrsync/file_backups/` in dated folders. Note that

* This only occurs for sync. Not for push or pull
* File moves that do not otherwise edit the data are not saved
    * Initial file-moves occur before backup
* Backups do not back up a deleted file on the side it was deleted on. You can
    * Use snapshots (see below)
    * Try to recover the file from the other side

Alternatively, built in (if allowed in the config file) is the ability to perform snapshots. They are stored in `.PBrsync/snapshots`. The initial snapshot **will make a fully copy** (and use extra space accordingly). However, after that, hard-links will be used. The appearance is like Apple's TimeMachine where the entire file system is shown.

**Warnings**: 

* Unlike sync, snapshots do not track moves.
* `push` and `pull` do not back up

If you wish to see the file sizes for the snapshots, `cd` to that folder then do
`du -sch *` which will list the *actual* storage usage

### Pruning older snapshots

Older *snapshots* may be pruned with the

    $ ./PBrsync snapshot --prune path/to/folder

mode. It will keep:
    
* 1 per week older than 30 days
* 1 per day for between 1 and 30 days old
* Keep all within the last day

Notes:

* `--prune` *will* also take a snapshot. Use `--prune-only` to not take a snapshot
* use `--prune --remote` to prune remote snapshots too!
* Only works (for now) on snapshots, not pre-sync backups

## Background: Requirements and Other Options

I will be the first to admit that this may not be as good as some other options out there. They were coded by better programmers and their end result is probably also better. But, my requirements removed most options.

My requirements were:

* Must work on current out-of-the-box set up for Mac and linux without installing anything
    * [**BitPocket**][BitPocket] and [**bsync**][bsync] require GNU utilities while mac uses BSD versions. Furthermore, bsync requires Python3 which isn't on the linux boxes I use.
    * [**Unison**][Unison] needs to be installed. And even if I were willing, I do not have root on all machines. There are also reports of issues related to version mis-match
* Must use minimal storage on non-hosts, and have easy-to-prune backups on server/host
    * DVCSs (e.g. [**git**][git], [**mercurial**][mercurial]) uses about double the space for every file plus any changes on all machines. It is also not super easy to prune older revisions and isn't clear if/when it works.
        * Tools like [git-annex](https://git-annex.branchable.com) need to be installed and don't really fix the other issues
    * Central VCS (e.g. [**SVN**][SVN]) are extremely hard to delete older revisions but they do use little space on the non-server machines
* Must never require the server polling the nodes. Because of firewalls, the nodes must do all of the push, pull, and "thinking" steps.
* Must detect conflicts and perform safe operations. (i.e. always keep both and have backups)
    * [**Rsync**][Rsync] alone is one-directional.
    * [**BitPocket**][BitPocket] doesn't seem to track file moves
* Must not use any 3rd party storage (no cloud providers). I must have full control and work on segregated networks.
* Must provide a backup system either through individual files or a file-system snapshot
    * Version control is overkill. Not sure if the other tools offer it except [**BitPocket**][BitPocket]
    
However, the design and methods are heavily inspired by [**BitPocket**][BitPocket] and [**bsync**][bsync] and I owe them a debt of gratitude. (and if your restrictions allow for them, I would check them out too!)

## Scalability

I have not performed a rigorous complexity analysis but I have since tried to improve the scaling to be roughly `O(N)` for `N` files plus `O(N*n)` for `n` moved files. This isn't perfect but the improvement made a big difference. And the moved file check is the the computational bottleneck.

I currently use this for, amongst other things, keeping my file-based photo-library up to date. For about 31,000 photos and 65G, a sync operation with on an already synchronized folder (that is, it needs to check for moves but doesn't actually have any) is about 10 seconds. (Before the improvement, it was 30). Note that these times are when running in PyPy.

## Logs

All logs are stored in `.PBrsync/logs`
 
## Known Limitations (and Edge cases)

*Reminder*: **Use at your own risk**

* For the most part, A and B are treated equally and any file conflicts are handled without deference to either. However, if there is a rename/move conflict between A and B (folder or file), the local (A) takes precedence
* Conflicts are handled by modification time relative to the last sync. If you have lots of files that are identical but different modification times *and*, the times may be updated but the content will remain.
    * This does not affect transfers since it would be fast, but may affect some other systems
* Most edge cases are considered, but there certainly may be some that haven't been. Please let me know if you discover one. See the Design Notes for my enumeration of them.
* There is no built-in system to handle if connection is lost between sync operations. However, since the system doesn't overwrite unless new, it *should* be fine. Still, have backups!!!
* There is no built in system to prevent concurrent operations. This is **not designed for multi-person use** (though it certainly *could* if careful about timing)
* Symbolic links are not followed
    * If you place `-L` into the rsync calls, it will copy them but move/delete detection will not be followed.
* Empty folders are *mostly* handled well, but sometimes they:
    * Can get transferred depending on exact rsync version
    * Get backed up if they are to be deleted and `localbackup` or `remotebackup` is `True`
    * If you move a folder, the old folder will *show* as deleted but everything else happens as you'd expect.
    * May get deleted if created as empty and then done with a sync
* **Possible Limitation**: Unlike vanilla rsync, this has to perform a lot more "thinking" and, more importantly, makes many (10!!!) remote hand shakes. This is most of the overhead. (Future versions may try to reduce this.)

## Setting Up SSH Keys

The typical call requires about 10 remote calls (see below) it is almost a requirement that you set up SSHkeys. Based on the comments for [BitPocket][BitPocket], it is better to *not* use a key password.

On both the local and remote machine, perform any ssh connection to generate the needed directories.

On your local machine:

    $ cd
    $ ssh-keygen -t rsa
    $ # Hit Enter twice.
    $ cat ~/.ssh/id_rsa.pub | ssh user@remote-system "mkdir -p ~/.ssh && cat >>  ~/.ssh/authorized_keys" 

That should be it. If not, search for it. 

### Remote Calls

Below are all of the remote opperations requiring a handshake

* (1) remote file snapshot 
* apply moves based on file renamed/moves
    * (1) Upload move queue
    * (1) apply
* (2) dry-run rsync push and pull
* (2) apply moves again to resolve conflicts
* (2) run rsync again, push and pull
* (1) updated remote snapshot 

## Other tips:

* Use `--silent` for cron to not print anything to screen
* Use Cron to perform backups
* If on a mac, use Automator to make a "Sync" button
* In my *limited* testing, this works well with `PyPy`
* Create an alias to run PBrsync (maybe with `PyPy`) so you can run it on any folder

## Future Additions:

On the list is to make this in Python3. However, many of the machines I use this on do not (yet) support it so I am stuck with 2.7.

In the future, there may be support for automatic snapshots before and/or after sync both locally and/or remote. At the moment, it is best to include them in your sync call

Also in the future will be a way to prune the backups and snapshots to only keep some number of them. For now, do it manually.

Finally, future versions may try to use a Python SSH module such as [Paramiko][Paramiko] (with the current method as a fall back) to reduce the number of connections. Or, it will try to use a persistant SSH connection. Either way, it will try to reduce the number of connections to a minimum.




[Paramiko]:http://www.paramiko.org/ 
[BitPocket]:https://github.com/sickill/bitpocket
[bsync]:https://github.com/dooblem/bsync
[Unison]:https://www.cis.upenn.edu/~bcpierce/unison/
[git]:https://git-scm.com/
[mercurial]:https://www.mercurial-scm.org/
[SVN]:https://subversion.apache.org/
[rsync]:https://rsync.samba.org/
