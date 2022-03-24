![GitHub](https://img.shields.io/github/license/rosalindfranklininstitute/Opt-ID?kill_cache=1) [![GitHub Workflow Status (branch)](https://github.com/rosalindfranklininstitute/Opt-ID/actions/workflows/ci.yml/badge.svg?branch=v2)](https://github.com/rosalindfranklininstitute/Opt-ID/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/rosalindfranklininstitute/Opt-ID/branch/v2/graph/badge.svg?token=pZp3wgitjN)](https://codecov.io/gh/rosalindfranklininstitute/Opt-ID)

# Docker and Singularity Containers

```
docker run -itd --name optid -v $(pwd):/tmp/repo/ -w /tmp/repo/ quay.io/rosalindfranklininstitute/opt-id:v2

docker exec optid python -m pytest --cov=/usr/local/Opt-ID/IDSort/src /usr/local/Opt-ID/IDSort/test/ --cov-report xml:coverage.xml

docker exec optid python -m IDSort.src.optid --help

docker stop optid
docker rm optid
```

```
singularity pull library://rosalindfranklininstitute/optid/optid:v2
singularity run optid_v2.sif python -m IDSort.src.optid --help
```

# Opt-ID
Code for the Optimisation of ID's using Python and Opt-AI

## Overview of how to use Opt-ID

Opt-ID is run is by providing:
- a main configuration file in YAML format which contains all the various
  parameters for the sort/shim job
- an existing directory in which output data will be written to

There are two main flags, `--sort` and `--shim`, to run sort and shim jobs. The
idea is that using either of these flags in conjunction with the YAML config
file will go through and run all the scripts that are used to produce
intermediate files and pass them around appropriately, so then there's only one
command needed to be executed to run a sort or shim job, and the YAML config
file is the single source of all the parameter information used for that
particular job.

There are several other processes that Opt-ID provides that are desired to be
done after a sort/shim but don't require the sequence of scripts that a
sort/shim job does (for example, the use of `compare.py` to compare a shimmed
genome to the original genome), so the `--sort` and `--shim` flags aren't able
to provide these sorts of processes. To do so, there are several shell scripts
that are autogenerated when a sort or shim job is run that can be executed.
These scripts run Opt-ID in the particular way that is needed to perform the
process, without the user needing to worry about extra configuration on top of
the YAML file.

Taking the `compare.py` example previously mentioned, a script would be
autogenerated after a shim job called `compare_shim.sh` that can be passed any
shimmed genome file in the data directory, and it will take care of calling
Opt-ID in the particular way it needs to in order to run the `compare.py` script
with the appropriate parameters. More details on how to use these autogenerated
shell scripts are below in the "Using the autogenerated shell scripts" section.

## Data directory

The data outputted by Opt-ID is split roughly into two categories:
- large files such as `.h5` files
- smaller files such as `.json`, `.mag`, `.sh` files

The smaller files get written to the directory passed as the second parameter to
Opt-ID, so if OptID was passed `/home/FedID/my_dir` then the smaller files would
get written to `/home/FedID/my_dir`.

The larger files get written to a directory within `/dls/tmp/FedID` whose path
is based on the user's FedID and also the name of the data directory passed to
Opt-ID. The name of the directory created in `/dls/tmp/FedID` will be the name
of the very last directory in the path passed to Opt-ID. For example, if the
path `/home/FedID/my_dir` is passed to Opt-ID, then the directory
`/dls/tmp/FedID/my_dir` will be created. Symlinks are then created in
`/home/FedID/my_dir` to point to the larger files inside
`/dls/tmp/FedID/my_dir`.

One reason behind having two separate directories containing different data
files is due to the large size of the `.h5` files produced by Opt-ID and not
having the space to put them just anywhere in the filesystem (`/dls/tmp` has
much more available space than, for example, the home directory associated to a
FedID). Another reason is that the automatic deletion of files in `/dls/tmp` can
be used to do some automatic periodic cleanup of old, large files.

### Intended usage

The intended usage of this dual-directory structure is that the smaller files
are written to somewhere away from `/dls/tmp` so then they're not deleted
periodically and can be referred to later if needed, whilst the larger files are
written to the user's directory in `/dls/tmp` so then they *are* deleted
periodically. Therefore, it is advised that the directory provided to Opt-ID is
not a directory in `/dls/tmp/FedID`; this is not only because of potential
deletion of the smaller files, but also because passing a directory in
`/dls/tmp/FedID` can cause some confusion regarding the directory that is
subsequently created by Opt-ID in `/dls/tmp/FedID`.

__In particular, it is advised that the directory passed to Opt-ID is one within
`/dls/technical/id`__, as this is where output data from other Opt-ID jobs has
typically been placed.

### Example directory structures

For example, if the directory `/dls/technical/id/test/` is passed to Opt-ID, the
expected directory structures right after having run a sort job on a cluster is
given below:

`/dls/technical/id/test/`:
- `test_sort.json` (file)
- `test_sort.mag` (file)
- `test_sort.h5 -> /dls/tmp/FedID/test/test_sort.h5` (symlink to a file)
- `generate_report.sh` (file)
- `restart_sort.sh` (file)
- `logfiles/` (directory)
- `genomes -> /dls/tmp/FedID/test/genomes/` (symlink to a directory)
- `process_genome_output -> /dls/tmp/FedID/test/process_genome_output/`
  (symlink to a directory)

`/dls/tmp/FedID/test/`:
- `test_sort.h5` (file, the symlink `/dls/technical/id/test/test_sort.h5` points
  to this file)
- `genomes/` (directory, the symlink `/dls/technical/id/test/genomes` points to
  this directory)
- `process_genome_output/` (directory, the symlink
  `/dls/technical/id/test/process_genome_output` points to this directory)

As another example, for the same directory being passed but instead a shim job
being run on a cluster, the expected directory structures right after the job
are:

`/dls/technical/id/test/`:
- `test_shim.json` (file)
- `test_shim.mag` (file)
- `test_shim.h5 -> /dls/tmp/FedID/test/test_shim.h5` (symlink to a file)
- `generate_report.sh` (file)
- `compare_shim.sh` (file)
- `logfiles/` (directory)
- `shimmed_genomes -> /dls/tmp/FedID/test/shimmed_genomes/` (symlink to a
  directory)
- `process_genome_output -> /dls/tmp/FedID/test/process_genome_output/`
  (symlink to a directory)

`/dls/tmp/FedID/test/`:
- `test_shim.h5` (file, the symlink `/dls/technical/id/test/test_shim.h5` points
  to this file)
- `shimmed_genomes/` (directory, the symlink
  `/dls/technical/id/test/shimmed_genomes` points to this directory)
- `process_genome_output/` (directory, the symlink
  `/dls/technical/id/test/process_genome_output` points to this directory)

Note that the filenames `test_sort.*` and `test_shim.*` are just placeholders
and have been chosen only for illustrative purposes, these files can be named as
desired in the YAML config file.

## Preliminary steps to be able to run Opt-ID

A process that is not done by Opt-ID is the transfer of magnet information in
the Excel files provided by the supplier to `.sim` files. To do so, from the
Excel files supplied by the supplier, create tab delimited `.sim` files of
magnetisation. This is a manual procedure done only on Windows. Note that,
currently, Opt-ID requires the magnet names in the `.sim` files to have leading
zeros that pad out the name to 3 digits. For example, instead of '1' it should
be '001'.

To get the code, clone the Opt-ID repo to the desired place in the filesystem.
To set up the environment for running Opt-ID on a Linux machine, in a terminal
run the following commands:

```
module load python/3
module load global/cluster
export PYTHONPATH=$PYTHONPATH:/path/to/Opt-ID
```

where `/path/to/Opt-ID` is the path to the root directory of the cloned repo.
(There is a change to how `python` is used to run the code which is detailed in
the next section, and so the third command is to enable `python` to find the
code in the repo).

## Running Opt-ID with the `python` command

The main script that is used for running Opt-ID is `IDSort/src/optid.py`. It
should be run using the syntax `python -m IDSort.src.optid` as opposed to
`python /path/to/Opt-ID/IDSort/src/optid.py`.

## Different options that Opt-ID can be run with

There are two sets of flags from which one flag from each set is mandatory to be
passed to Opt-ID, and the rest are optional and have sensible default values if
they are not provided.

The mandatory sets of flags are

- `--sort` vs `--shim`
- `--cluster-on` vs `--cluster-off`

where only one flag from each bullet point should be provided.

Examples of running Opt-ID with the bare mininum flags and parameters it needs
are:

```
python -m IDSort.src.optid --sort --cluster-on /path/to/yaml /path/to/data/dir
python -m IDSort.src.optid --shim --cluster-off /path/to/yaml /path/to/data/dir
```

### `--sort` and `--shim`

These are used for specifying what type of job is desired.

### `--cluster-on` and `--cluster-off`

These are used for specifying whether the job is run on the local machine or
submitted to run on a cluster.

#### `--num-threads`, `--queue`, and `--node-os`

These are used in conjunction with `--cluster-on`. Some examples of using these
flags would be

```
python -m IDSort.src.optid --sort --cluster-on --node-os rhel7 /path/to/yaml /path/to/data/dir
python -m IDSort.src.optid --shim --cluster-on --queue low.q /path/to/yaml /path/to/data/dir
```

#### `--seed` and `--seed-value`

These are used in conjunction with `--cluster-off`. `--seed` is used to specify
that the random number generator (RNG) should be seeded and thus produce the
same output across multiple runs with the same parameters. `--seed-value` is
specified if a particular value to seed the RNG is desired (by default its value
is 1). Some examples of using these flags would be

```
python -m IDSort.src.optid --sort --cluster-off --seed /path/to/yaml /path/to/data/dir
python -m IDSort.src.optid --shim --cluster-off --seed --seed-value 30 /path/to/yaml /path/to/data/dir
```
## YAML config files

The YAML config files contain the parameters used by the various scripts that
Opt-ID runs. The top-level sections of the YAML config files are the script
names minus the `.py` and the subsections are the different parameters passed to
that particular script. For the most part, the subsection names are exactly the
same as the script parameters they're associated to, for example, the
`id_setup.py` script has a `--periods` flag, and the YAML subsection
corresponding to that parameter is `id_setup.periods`.

A few exceptions exist to try and be more descriptive with what the parameter
is, for example, `process_genome.py` refers to the files it's given as elements
of the `args` list, but in the YAML the corresponding subsection for a shim job
is `process_genome.readable_genome_file` which is hopefully a more useful
description.

Examples of YAML config files can be found in the `IDSort/example_configs`
directory. There are some placeholder values in these config files that aren't
valid values for their associated section in the YAML, and the following
sections detail the changes that need to be made to the example config files to
get them in a state ready to run a job.

### Sort config example

There are three values that need to be changed:
- `magnets.hmags`
- `magnets.hemags`
- `magnets.htmags`

Their values should be absolute paths to any `.sim` files of the relevant type.

### Shim config example

There are five values that need to be changed:
- `magnets.hmags`
- `magnets.hemags`
- `magnets.htmags`
- `process_genome.readable_genome_file`
- `mpi_runner_for_shim_opt.bfield_filename`

The first three are the same as in the sort config example. The value of
`process_genome.readable_genome_file` should be an absolute path to the `.inp`
file that is used to start the shim job from. The value of
`mpi_runner_for_shim_opt.bfield_filename` should be an absolute path to the
`.h5` file that is converted from `.bfield` files that are produced by igor.

Note that, currently, the use of the `igor2h5.py` script hasn't yet been
integrated into the YAML configuration file for Opt-ID, so the process of
converting `.bfield` data into `.h5` data is one that needs to be done by
manually executing the `igor2h5.py` script (or by any other means) prior to
running a shim job with Opt-ID.

## Using the autogenerated shell scripts

All the autogenerated scripts can be executed from anywhere in the filesystem,
it's not necessary for the current working directory to be the same directory
that the script is in.

Due to the facts that

- these scripts are generated on a job-by-job basis and are only meant to be run
  for the particular data within the directory the scripts are in
- the structure of the data directories are fixed and known in advance

when it comes to passing parameters to these scripts they are aware of the
specific directories that the files they're expecting should be in, so only
filenames need to be given to them and not absolute or even relative filepaths.
Concrete examples are given below in the `generate_report.sh` and
`compare_shim.sh` sections that hopefully explain in more detail how to pass
parameters to these scripts.

### `generate_report.sh`

This script is used to create a report with some useful data visualisation in a
PDF file. For a sort job it can be passed multiple `.genome` and `.inp` files,
and for a shim job it can be passed multiple `.h5` files that are associated to
the "full genomes" (as opposed to the smaller-sized "compare genomes") in the
shim output.

For a sort job, Opt-ID will look in both the `genomes/` and
`process_genome_output/` directories for the given `.genome` and `.inp` files,
and for a shim job Opt-ID will look in the `shimmed_genomes/` directory for the
given `.h5` files. Therefore, the parameters passed to `generate_report.sh`
should only be the filenames and not filepaths.

For example, for a sort job, the correct way to pass a genome and a `.inp` file
to the script would be

```
/path/to/generate_report.sh foo.genome bar.inp
```

as opposed to

```
/path/to/generate_report.sh genomes/foo.genome process_genome_output/bar.inp
```

Another example: for a shim job, the correct way to pass `.h5` files to the
script would be

```
/path/to/generate_report.sh foo.h5 bar.h5
```

as opposed to

```
/path/to/generate_report.sh shimmed_genomes/foo.h5 shimmed_genomes/bar.h5
```

An optional `--report-filename` flag can be passed before the files to specify
the name of the PDF file, and genome reports are stored in the `genome_reports/`
directory within the directory passed to Opt-ID. Report filenames should have a
`.pdf` extension to enable a simple check between the report filename parameter
and `.genome`/`.inp` file parameters that follow it. The `--report-filename`
option can be omitted and in that case the report filename will be a
concatenation of all the filenames passed with an underscore character "_" as
the separator between the filenames.

An example of using the `--report-filename` flag is

```
/path/to/generate_report --report-filename report.pdf foo.genome bar.inp
```

### `restart_sort.sh`

This script requires no parameters and can be run simply as
`/path/to/restart_sort.sh`, Opt-ID will take care of loading the YAML config of
the previous sort job and will use all the same flags and paramters as the
original sort job. One example is that if the original sort job was run on a
cluster, so will the restart-sort job, and another example is that the same
`.json`, `.mag` and `.h5` (lookup table) files from the original sort job will
be reused in the restart-sort job instead of being regenerated.

### `compare_shim.sh`

This can be passed a single `.genome` file that is in the `shimmed_genomes/`
directory and it will generate a human readable diff between the original and
shimmed genomes that will be written to the `shim_diffs/` directory. It's not
necessary to pass the original genome to this script, Opt-ID will take care of
finding it so only the shimmed genome needs to be given as a parameter.

Similarly to what `generate_report.sh` does, `compare_shim.sh` will look in the
`shimmed_genomes/` directory so only filenames should be passed to it and not
filepaths. An example of using this script would be:

```
/path/to/compare_shim.sh foo.genome
```

An optional `--diff-filename` flag can be passed before the shimmed genome file
to specify the filename of the human readable diff. Currently Opt-ID appends a
`.txt` extension to the filename so it's not necessary to put that in the
parameter. Again, similarly to what `generate_report.sh` does, if this flag is
omitted then the diff filename is a concatenation of the original genome and
shimmed genome filenames with an underscore character as the separator, and then
also prepended with `shim_`. For example, if the original genome is `foo.genome`
and the shimmed genome is `bar.genome`, then if the `--diff-filename` flag is
omitted then the diff filename would be `shim_foo.genome_bar.genome.txt`. An
example of using the `--diff-filename` flag is

```
/path/to/compare_shim.sh --diff-filename my_shim foo.genome
```

## "Hidden" options of Opt-ID

There are several options that Opt-ID has but are only meant to be used by the
autogenerated shell scripts and not intended to be invoked directly by a user;
therefore, these options aren't of much interest to users and only of potential
interest to developers. The following are just some useful notes to any
developers viewing this document:

- these options are related to those kinds of processes that a user would want
  to do that aren't full sort/shim jobs that were referred to in the "Overview
  of how to use Opt-ID" section of this document
- these options are all used by the autogenerated shell scripts that were also
  referred to in the "Overview of how to use Opt-ID" section, hence why the
  users need not directly use them, the autogenerated scripts should take care
  of using these "hidden options" where necessary
- these are also processes that are done after a sort/shim, so they assume the
  existence of a YAML config that has already been used for the sort/shim job,
  as well as any output data from a sort/shim job

### `--generate-report`

This option starts off the process of using the
`IDSort/src/genome_report_template.ipynb` file to generate a Jupyter notebook
file, and then running it to produce a PDF report.

### `--restart-sort`

This option starts off the process of reusing the same YAML config file that was
used for the sort job to get all the parameters used for the original sort job,
and then running Opt-ID to generate genomes from an initial population as
opposed to generating genomes from scratch.

### `--compare-shim`

This option starts off the process of comparing the given shimmed genome to the
original genome that was used to start the shim job.

## Running the tests

Navigate to the root directory of the Opt-ID repo:

```
cd /path/to/Opt-ID
```

To run all the tests:

```
python -m pytest IDSort/test/
```

To run a particular test in the `test/` directory, it can be specified in the
path in the above command. For example, to run `IDSort/test/magnets_test.py`:

```
python -m pytest IDSort/test/magnets_test.py
```