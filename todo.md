# To Do list

This is incomplete

## SSH Related

* Persistant SSH connection
    * [Paramiko][Paramiko]?
    * Bash-based?
* Compressed SSH transfers
    * May also compress file-lists

[Paramiko]:http://www.paramiko.org/ 

## Speed up

* `multiprocessing` for file parsing?
    * Requires a better profiling of times
* Compression of file lists?

## General Usage

* Automatic snapshot support
    * For now, include in a script, etc
* Cron documentation

## Distant Future

* Support for blocking of concurrent sync
    * Could do with a temp lock file but may cause problems when interrupted.
    * Could I make the entire sync atomic?
* Add my tester
    * One exists but it isn't very clean and I haven't used it since putting this into production
    * Could use a better testing framework all together!

