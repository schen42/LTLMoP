import sys
import re
import time
import pycudd
import strategy
import logging

# NOTE: This module requires a modified version of pycudd!!
# See src/etc/patches/README_PYCUDD for instructions.

class BDDStrategy(strategy.Strategy):
    def __init__(self):
        super(BDDStrategy, self).__init__()

        # We will have a state collection just in order to provide a context
        # for states (FIXME?)
        self.states = strategy.StateCollection()

        self.strategy = None
        self.var_name_to_BDD = {}
        self.BDD_to_var_name = {}
        self.var_num_to_var_name = []
        self.jx_vars = []
        self.strat_type_var = None

        self.mgr = pycudd.DdManager()
        self.mgr.SetDefault()

        # Choose a timer func with maximum accuracy for given platform
        if sys.platform in ['win32', 'cygwin']:
            self.timer_func = time.clock
        else:
            self.timer_func = time.time

    def loadFromFile(self, filename):
        """
        Load in a strategy BDD from a  file produced by a synthesizer,
        such as JTLV or Slugs.
        """

        logging.info("Loading strategy from file '{}'...".format(filename))

        a = pycudd.DdArray(1)

        tic = self.timer_func()

        # Load in the actual BDD itself
        # Note: We are using an ADD loader because the BDD loader
        # would expect us to have a reduced BDD with only one leaf node
        self.mgr.AddArrayLoad(pycudd.DDDMP_ROOT_MATCHLIST,
                              None,
                              pycudd.DDDMP_VAR_MATCHIDS,
                              None,
                              None,
                              None,
                              pycudd.DDDMP_MODE_TEXT,
                              filename, None, a)

        # Convert from a binary (0/1) ADD to a BDD
        self.strategy = self.mgr.addBddPattern(a[0])

        # Load in meta-data
        with open(filename, 'r') as f:
            # Seek forward to the start of the variable definition section
            line = ""
            while not line.startswith("# Variable names:"):
                line = f.readline()

            # Parse the variable definitions
            for line in f:
                m = re.match(r"^#\s*(?P<num>\d+)\s*:\s*<(?P<name>\w+'?)>", line)

                # We will stop parsing as soon as we encounter an invalid line
                # Note: This includes empty lines!
                if m is None:
                    break

                varname = m.group("name")
                varnum = int(m.group("num"))

                #### TEMPORARY HACK: REMOVE ME AFTER OTHER COMPONENTS ARE UPDATED!!!
                # Rewrite proposition names to make the old bitvector system work
                # with the new one
                varname = re.sub(r"^bit(\d+)('?)$", r'region_b\1\2', varname)
                #################################################################

                if varname == "jx":
                    self.jx_vars.append(self.mgr.IthVar(varnum))
                elif varname == "strat_type":
                    self.strat_type_var = self.mgr.IthVar(varnum)
                else:
                    self.BDD_to_var_name[self.mgr.IthVar(varnum)] = varname
                    self.var_name_to_BDD[varname] = self.mgr.IthVar(varnum)

                self.var_num_to_var_name.append(varname)
                # TODO: check for consecutivity

        toc = self.timer_func()

        logging.info("Loaded in {} seconds.".format(toc-tic))


    def searchForStates(self, prop_assignments, state_list=None):
        """ Returns an iterator for the subset of all known states (or a subset
            specified in `state_list`) that satisfy `prop_assignments`. """

        if state_list is None:
            # TODO: we only need to calculate this once
            all_primed_vars_bdd = self.propAssignmentToBDD({k:True for k in self.states.getPropositions(expand_domains=True)}, use_next=True)
            state_list_bdd = self.strategy.ExistAbstract(all_primed_vars_bdd)
        else:
            state_list_bdd = self.stateListToBDD(state_list)

        satisfying_state_list_bdd = state_list_bdd & self.propAssignmentToBDD(prop_assignments)

        return self.BDDToStates(satisfying_state_list_bdd)

    def satOne(self, bdd, var_names):
        for vn in var_names:
            test = bdd & ~self.var_name_to_BDD[vn]
            if test:
                bdd = test
            else:
                bdd &= self.var_name_to_BDD[vn]

        return bdd

    def satAll(self, bdd, var_names):
        while bdd:
            one_sat = self.satOne(bdd, var_names)
            yield one_sat
            bdd &= ~one_sat

    def BDDToStates(self, bdd):
        for one_sat in self.satAll(bdd, self.states.getPropositions(expand_domains=True)):
            yield self.BDDToState(one_sat)

    def BDDToState(self, bdd):
        prop_assignments = {k: bool(bdd & self.var_name_to_BDD[k])
                            for k in self.states.getPropositions(expand_domains=True)}
        # TODO: jx?
        return self.states.addNewState(prop_assignments)

    def printStrategy(self):
        """ Dump the minterm of the strategy BDD.  For debugging only. """
        self.strategy.PrintMinterm()

    def stateListToBDD(self, state_list, use_next=False):
        return reduce(lambda bdd1, bdd2: bdd1 | bdd2,
                      (self.stateToBDD(s, use_next) for s in state_list))

    def propAssignmentToBDD(self, prop_assigments, use_next=False):
        """ Create a BDD that represents the given *binary* proposition
            assignments (expressed as a dictionary from prop_name[str]->prop_val[bool]).
            If `use_next` is True, all variables will be primed. """

        # Start with the BDD for True
        bdd = self.mgr.ReadOne()

        # Add all the proposition values one by one
        for prop_name, prop_value in prop_assigments.iteritems():
            if use_next:
                prop_name += "'"

            if prop_value:
                bdd &= self.var_name_to_BDD[prop_name]
            else:
                bdd &= ~self.var_name_to_BDD[prop_name]

        return bdd

    def stateToBDD(self, state, use_next=False):
        """ Create a BDD that represents the given state.
            If `use_next` is True, all variables will be primed. """

        return self.propAssignmentToBDD(state.getAll(expand_domains=True), use_next)

    def getTransitions(self, state, jx, strat_type):
        # 0. The strategies that do not change the justice pursued
        # 1. The strategies that change the justice pursued
        if strat_type == "Y":
            strat_type_bdd = ~self.strat_type_var
        elif strat_type == "Z":
            strat_type_bdd = self.strat_type_var
        else:
            print "bad strat type", strat_type
            return None
        cand = self.strategy & state & self.getJxBDD(jx) & strat_type_bdd
        return cand

    def getJxBDD(self, jx):
        jx_bdd = self.mgr.ReadOne()
        # TODO: safety checks
        for i, bit in enumerate(("{:0"+str(len(self.jx_vars))+"b}").format(jx)[::-1]): # lesser significant bits have lower varids
            if bit == "0":
                jx_bdd &= ~self.jx_vars[i]
            elif bit == "1":
                jx_bdd &= self.jx_vars[i]
            else:
                print "this bit is wack", bit
        return jx_bdd

    def cubeToString(self, cube):
        cube = list(cube)
        for i, v in enumerate(cube):
            if v == 0:
                cube[i] = "{}".format(self.var_num_to_var_name[i])
            elif v == 1:
                cube[i] = "!{}".format(self.var_num_to_var_name[i])
            elif v == 2:
                #cube[i] = "({})".format(self.var_num_to_var_name[i])
                cube[i] = "--"
            else:
                print "this cube is wack", cube
        return ", ".join(cube)

    def printSats(self, bdd):
        for cube in bdd:
            print self.cubeToString(cube)
            #print pycudd.cube_tuple_to_str(cube)

    # getTransitions or whaterver else FSA does


def BDDTest(spec_file_name):
    # TODO: move generalized test to main Strategy class
    import project
    import pprint

    proj = project.Project()
    proj.loadProject(spec_file_name)
    rfi = proj.loadRegionFile(decomposed=True)
    bdd_file_name = proj.getFilenamePrefix()+'.bdd'
    s = BDDStrategy()
    region_domain = strategy.Domain("region", rfi.regions, strategy.Domain.B0_IS_MSB)
    s.configurePropositions(proj.enabled_sensors, proj.enabled_actuators + proj.all_customs + [region_domain])
    s.loadFromFile(bdd_file_name)

    initial_region = rfi.regions[rfi.indexOfRegionWithName("p3")]

    test_state = s.states.addNewState({"region": initial_region,
                                       "person": True,
                                       "radio": True,
                                       "pick_up": False,
                                       "drop": False,
                                       "carrying_item": False,
                                       "hazardous_item": False})
    print "Test state:"
    s.stateToBDD(test_state).PrintMinterm()
    #s.printStrategy()

    # TODO: should we be using region names instead of objects to avoid
    # weird errors if two copies of the same map are used?
    #print "0th state:", s.searchForOneState({})

    #TODO: need to expand prop_assignment domains... ugh
    #start_state = s.searchForOneState({"region": initial_region, "person": False})
    start_state = s.searchForOneState({"person": False})
    print "Start state:", start_state

    print "Successors:"
    pprint.pprint(s.findTransitionableStates({}, from_state=start_state))

    #s.exportAsDotFile("test.dot")

if __name__ == "__main__":

    BDDTest(sys.argv[1])
    ##strategy.printStrategy()
    #print " ".join(strategy.var_num_to_var_name)
    #curr_state = strategy.stateToBDD(None)
    #strategy.printSats(curr_state)
    #strategy.printSats(strategy.getJxBDD(1))
    #tr = strategy.getTransitions(curr_state, 1, "Y")
    #strategy.printSats(tr)
    ##print "---"
    ##strategy.printSats(strategy.strategy)
