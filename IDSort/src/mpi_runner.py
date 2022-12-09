# Copyright 2017 Diamond Light Source
# 
# Licensed under the Apache License, Version 2.0 (the "License"); 
# you may not use this file except in compliance with the License. 
# You may obtain a copy of the License at
# 
# http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, 
# software distributed under the License is distributed on an 
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, 
# either express or implied. See the License for the specific 
# language governing permissions and limitations under the License.


# Run this script with a suitable mpirun command. 
# The DLS controls installation of h5py is built against openmpi version 1.6.5.
# Note that the current default mpirun in the controls environment (module load controls-tools)
# is an older version of mpirun - so use the full path to mpirun as demonstrated in the
# example below.
#
# For documentation, see: http://www.h5py.org/docs/topics/mpi.html
# 
# Example:
# /dls_sw/prod/tools/RHEL6-x86_64/openmpi/1-6-5/prefix/bin/mpirun -np 5 dls-python parallel-hdf5-demo.py
#


# rn this with the following command
# qsub -pe openmpi 80 -q low.q -l release=rhel6 /home/ssg37927/ID/Opt-ID/IDSort/src/v2/mpijob.sh --iterations 100
#
#

import os
import random
import itertools

import json
import shutil

import h5py

import numpy as np

import socket
from mpi4py import MPI

from .magnets import Magnets, MagLists
from .genome_tools import ID_BCell

from .field_generator import generate_reference_magnets,   \
                             generate_bfield,              \
                             calculate_bfield_phase_error

from .logging_utils import logging, getLogger, setLoggerLevel
logger = getLogger(__name__)


def mutations(c, e_star, fitness, scale):
    inverse_proportional_hypermutation =  abs(((1.0 - (e_star / fitness)) * c) + c)
    a = random.random()
    b = random.random()
    hypermacromuation = abs((a - b) * scale)
    return int(inverse_proportional_hypermutation + hypermacromuation)


def process(options, args):

    if hasattr(options, 'verbose'):
        setLoggerLevel(logger, options.verbose)

    logger.debug('Starting')

    output_path = args[0]

    if options.singlethreaded:
        # Who am I within the set of compute nodes
        comm_rank, comm_size, comm_ip = (0, 1, 'localhost')

        # No synchronization needed in single node case
        def barrier():
            pass

        # No exchange needed in single node case
        def exchange_genomes(local_population):
            return local_population

    else:
        # Who am I within the set of compute nodes
        comm_rank, comm_size, comm_ip = (MPI.COMM_WORLD.rank, MPI.COMM_WORLD.size,
                                         socket.gethostbyname(socket.gethostname()))

        # Use a collective MPI barrier to synchronize all compute nodes
        def barrier():
            MPI.COMM_WORLD.Barrier()

        # TODO need test case that uses multiple MPI nodes to test this communication works properly
        # Exchange local population of genomes between compute nodes so that every node has the global population
        def exchange_genomes(local_population):
            return list(itertools.chain.from_iterable(MPI.COMM_WORLD.alltoall([local_population] * comm_size)))

    logger.info('Node %3d of %3d @ [%s]', comm_rank, comm_size, comm_ip)

    if options.seed:
        logger.info('Random seed set to %d', int(options.seed_value))
        random.seed(int(options.seed_value + comm_rank))

    # Attempt to load the ID json data
    try:
        logger.info('Loading ID info from json [%s]', options.id_filename)
        with open(options.id_filename, 'r') as fp:
            info = json.load(fp)

    except Exception as ex:
        logger.error('Failed to load ID info from json [%s]', options.id_filename, exc_info=ex)
        raise ex

    # Attempt to load the ID's lookup table for the eval points defined in the JSON file
    try:
        logger.info('Loading ID lookup table [%s]', options.lookup_filename)

        if options.singlethreaded:
            worker_lookup = options.lookup_filename
        else:
            worker_lookup = f'{options.lookup_filename}.worker-{comm_rank}'
            shutil.copy(options.lookup_filename, worker_lookup)

        with h5py.File(worker_lookup, 'r') as fp:
            logger.debug(list(fp.keys()))
            lookup = {}
            for beam in info['beams']:
                logger.debug(beam['name'])
                logger.debug(fp[beam['name']].shape)
                lookup[beam['name']] = fp[beam['name']][...]
                logger.debug('Loaded beam [%s] with shape [%s]', beam['name'], lookup[beam['name']].shape)


    except Exception as ex:
        logger.error('Failed to load ID lookup table [%s]', options.lookup_filename, exc_info=ex)
        raise ex

    # Attempt to load the real magnet data
    try:
        logger.info('Loading ID magnets [%s]', options.magnets_filename)
        magnet_sets = Magnets()
        magnet_sets.load(options.magnets_filename)

    except Exception as ex:
        logger.error('Failed to load ID info from json [%s]', options.magnets_filename, exc_info=ex)
        raise ex

    # From loaded data construct a perfect magnet array that the loss will be computed with respect to
    logger.info('Constructing perfect reference magnets to shadow real magnets and ideal bfield')
    ref_magnet_sets  = generate_reference_magnets(magnet_sets)
    ref_magnet_lists = MagLists(ref_magnet_sets)
    ref_bfield       = generate_bfield(info, ref_magnet_lists, ref_magnet_sets, lookup)

    ref_phase_error, ref_trajectories = calculate_bfield_phase_error(info, ref_bfield)
    logger.debug('Perfect bfield phase error [%s]', ref_phase_error)

    # TODO currently broken, fix or remove
    # ref_strx, ref_strz = calculate_trajectory_straightness(info, ref_trajectories)
    # logger.debug('Perfect bfield trajectory straightness [%s] [%s]', ref_strx, ref_strz)

    barrier()

    # Filter the population for unique fitness values keeping the oldest genome when there are genomes with the same fitness
    def filter_genomes(population):
        genomes = {}
        for genome in population:
            # TODO remove dependency on filename scientific notation encoding
            genome_key = f'{genome.fitness:1.8E}'

            # Keep the genome with the highest age if there are two with the same fitness value
            if (genome_key not in genomes.keys()) or \
               ((genome_key in genomes.keys()) and (genomes[genome_key].age < genome.age)):
                genomes[genome_key] = genome

        # Filter the population to remove genomes that have an age higher than the maximum allowed age
        population = filter((lambda genome : (genome.age < options.max_age)), genomes.values())

        # Sort the population so that the first one is the best genome
        population = sorted(population, key=(lambda genome : genome.fitness))

        # TODO this places all the best genomes on node with rank 0, consider replacing with strided distribution
        #  so all nodes get some of the best and some of the worse genomes
        population = population[(options.setup * comm_rank):(options.setup * (comm_rank + 1))]
        # population = population[comm_rank::comm_size][:options.setup] # Strided distribution of genomes

        return population

    # Synchronize nodes sequentially to print diagnostics about local genome populations
    def log_genomes(population):
        # Early return if logger is not set to at least output INFO messages
        if not logger.isEnabledFor(logging.INFO): return

        # Synchronize nodes sequentially to print diagnostics about local genome populations
        for rank in range(comm_size):
            barrier()
            if rank != comm_rank: continue

            # Compute the min, max, and average for the fitness, age, and mutations for each genome in the local population
            fitness_stats, age_stats, mutation_stats = [(np.min(data), np.max(data), np.mean(data))
                                                        for data in zip(*[(genome.fitness, genome.age, genome.mutations)
                                                                          for genome in population])]

            logger.info('Node %3d of %3d has %d genomes with fitness (min %1.8E, max %1.8E, avg %1.8E) '
                        'age (min %0.0f, max %0.0f, avg %0.2f) mutations (min %0.0f, max %0.0f, avg %0.2f)',
                        comm_rank, comm_size, len(population), *fitness_stats, *age_stats, *mutation_stats)

            if logger.isEnabledFor(logging.DEBUG):
                for genome_index, genome in enumerate(population):
                    logger.debug('Node %3d of %3d Genome %3d of %3d %s with fitness %1.8E age %d mutations %d',
                                 comm_rank, comm_size, genome_index, len(population), genome.uid,
                                 genome.fitness, genome.age, genome.mutations)

    # Initial estar used for sampling mutations
    estar = options.e

    # Array to hold the current population
    population = []

    # Create genomes on master node only and communicate them to all nodes for consistency
    if comm_rank == 0:
        if options.restart:
            # If continuing an existing sort job then load saved genomes and sample random genomes to bring us up to the full population

            # Sort genome filenames to ensure test consistency
            genome_names = sorted(os.listdir(output_path))
            for genome_index, genome_name in enumerate(genome_names):
                genome_path = os.path.join(output_path, genome_name)

                # Attempt loading the current genome file and adding it to the population
                # Sorting paths before ensures that first genome is the one with the best fitness
                try:
                    logger.info('Loading genome %03d of %03d [%s]', genome_index, len(genome_names), genome_path)
                    genome = ID_BCell()
                    genome.load(genome_path)
                    population.append(genome)

                except Exception as ex:
                    logger.error('Failed to genome [%s]', genome_path, exc_info=ex)
                    raise ex

            # Assert that if we are restarting the optimization at least one existing genome was successfully loaded
            if len(population) == 0:
                error_message = 'Cannot restart optimization as no existing genomes were found!'
                logger.error(error_message)
                raise Exception(error_message)

            # If the number of loaded genomes is smaller than the target population size, then
            # initialize the rest of the population using children mutated for the first (best) genome that was loaded
            if len(population) < options.setup:
                logger.info('%d of %d expected genomes were discovered and loaded', len(population), options.setup)
                num_children  = options.setup - len(population)
                num_mutations = 20
                logger.info('Sampling the remaining %d genomes from the best genome using %d mutations each', num_children, num_mutations)
                population   += population[0].generate_children(num_children, num_mutations, info, lookup,
                                                                magnet_sets, ref_trajectories)

        else:
            # If starting a new sort then generate a population of randomly initialized genomes

            logger.info('Creating %d randomly initialized genomes', options.setup)
            for genome_index in range(options.setup):
                logger.debug('Sampling random genome %d of %d', genome_index, options.setup)

                # Create a new random genome and add it to the population
                magnet_lists = MagLists(magnet_sets)
                magnet_lists.shuffle_all()
                genome = ID_BCell()
                genome.create(info, lookup, magnet_sets, magnet_lists, ref_trajectories)
                population.append(genome)

        logger.debug('Initial population created')

    population = filter_genomes(exchange_genomes(population))
    log_genomes(population)

    # Checkpoint best genome with lowest fitness from the master node
    if comm_rank == 0:
        try:
            best_genome = population[0]
            logger.info('Saving best genome %s with fitness %1.8E age %d mutations %d',
                        best_genome.uid, best_genome.fitness, best_genome.age, best_genome.mutations)
            best_genome.save(output_path)

        except Exception as ex:
            logger.error('Failed to save best genome to [%s]', output_path, exc_info=ex)
            raise ex

    # Perform multiple iterations of mutations and communications
    for iteration in range(options.iterations):
        barrier()
        if comm_rank == 0:
            logger.info('Iteration %d', iteration)

        new_population = []

        # Apply mutations to each genome in the local population
        for genome_index, genome in enumerate(population):

            # For each genome we will generate multiple children by applying randomized numbers of random mutations to the current genome
            num_children  = options.setup
            num_mutations = mutations(options.c, estar, genome.fitness, options.scale)

            # The new population will include the current genome and the random children of the current genome
            new_population += [genome] + genome.generate_children(num_children, num_mutations, info, lookup,
                                                                  magnet_sets, ref_trajectories)

        # Exchange the genomes between compute nodes filter them, and redistribute them fairly between nodes for the next iteration
        population = filter_genomes(exchange_genomes(new_population))

        estar = population[0].fitness * 0.99
        logger.info('Node %3d of %3d updated estar %0.8f', comm_rank, comm_size, estar)

        # TODO should checkpoint all genomes from all nodes so we can restart from exactly where we left off,
        #      random number generator will not be restored properly unless handled explicitly
        # Checkpoint best genome with lowest fitness from the master node
        if comm_rank == 0:
            try:
                best_genome = population[0]
                logger.info('Saving best genome %s with fitness %1.8E age %d mutations %d',
                            best_genome.uid, best_genome.fitness, best_genome.age, best_genome.mutations)
                best_genome.save(output_path)

            except Exception as ex:
                logger.error('Failed to save best genome to [%s]', output_path, exc_info=ex)
                raise ex

        log_genomes(population)

    barrier()

    logger.debug('Halting')

if __name__ == "__main__":
    import optparse

    usage = "%prog [options] run_directory"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-v', '--verbose', dest='verbose', help='Set the verbosity level [0-4]', default=0, type='int')
    parser.add_option("-f", "--fitness", dest="fitness", help="Set the target fitness", default=0.0, type="float")
    parser.add_option("-s", "--setup", dest="setup", help="set number of genomes to create in setup mode", default=5, type='int')
    parser.add_option("-i", "--info", dest="id_filename", help="Set the path to the id data", required=True, type="string")
    parser.add_option("-l", "--lookup", dest="lookup_filename", help="Set the path to the lookup table", required=True, type="string")
    parser.add_option("-m", "--magnets", dest="magnets_filename", help="Set the path to the magnet description file", required=True, type="string")
    parser.add_option("-a", "--maxage", dest="max_age", help="Set the maximum age of a genome", default=10, type='int')
    parser.add_option("--param_c", dest="c", help="Set the OPT-AI parameter c", default=10.0, type='float')
    parser.add_option("--param_e", dest="e", help="Set the OPT-AI parameter eStar", default=0.0, type='float')
    parser.add_option("--param_scale", dest="scale", help="Set the OPT-AI parameter scale", default=10.0, type='float')
    parser.add_option("-r", "--restart", dest="restart", help="Don't recreate initial data", action="store_true", default=False)
    parser.add_option("--iterations", dest="iterations", help="Number of Iterations to run", default=1, type='int')
    parser.add_option("--singlethreaded", dest="singlethreaded", help="Set the program to run as singlethreaded", action="store_true", default=False)
    parser.add_option("--seed", dest="seed", help="Seed the random number generator or not", action="store_true", default=False)
    parser.add_option("--seed_value", dest="seed_value", help="Seed value for the random number generator")

    (options, args) = parser.parse_args()

    try:
        process(options, args)
    except Exception as ex:
        logger.critical('Fatal exception in mpi_runner::process', exc_info=ex)
