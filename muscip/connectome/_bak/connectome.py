import networkx

class TNConnectome(networkx.Graph):
    """Connectome as defined by me!"""

    def __init__(self):
        networkx.Graph.__init__(self)

    def edge_observations_for_key(self, key, include_info=True, node_name_key=None):
        """Return record for a given key in the form of a dictionary.

        Inputs::

          key: key for which to export - key must contain no more than
               a single value for each edge

          include_info: (Boolean) should export include info

          node_name_key: if provided, will use information stored in
                         the node key, to label edges, if not
                         provided, will use node labels - edges will
                         take on the form of nodeA-nodeB

        """
        try:
            if include_info:
                try:
                    from copy import copy
                    data = copy(self.graph['info'])
                except KeyError:
                    print "No global info found for connectome."
                    data = dict()                    
                except Exception, e:
                    print e
            else:
                data = dict()
                # for every edge, get data and put in result
            for a,b in self.edges_iter():
                if node_name_key is not None:
                    # get node names
                    nodeA = self.node[a][node_name_key]
                    nodeB = self.node[b][node_name_key]
                else:
                    nodeA = a
                    nodeB = b
                data["%s-%s" % (str(nodeA), str(nodeB))] = self[a][b][key]
            return data
        except Exception, e:
            print e
            return None

    def matrix_for_key(self, key, force_symmetric=True,
                       binarize=False, number_of_nodes=None,
                       zero_diagonal=True):
        """Return a NxN matrix for given connectome and key. The
        connection matrix is returned as a numpy ndarray.

        """
        ##TODO: Add functionality for fixed desnity
        # create our new shiny connection matrix
        import numpy
        if number_of_nodes is None:
            n = max(self.nodes())
        else:
            n = number_of_nodes
        new_cmat = numpy.zeros((n,n))

        # extract the value for key for every edge in the given connectome
        for i,j in self.edges_iter():
            new_cmat[i-1][j-1] = self[i][j][key]
                
        # do we need to do anything regarding symmetry?
        if force_symmetric and (new_cmat - new_cmat.T != 0).any():
            #...if one-sided (no information below diagonal)
            if (numpy.tril(new_cmat,-1) == 0).all():
                # project above diagonal onto below diagonal
                new_cmat += numpy.tril(new_cmat.T, -1)
                #...else, we will assume two-sided unequal
            else:
                # our solution will be to take the mean of each pair of
                # reflected indices
                new_cmat = (new_cmat + new_cmat.T ) / 2.0

        # if we need to binarize...
        if binarize:
            new_cmat = new_cmat >= 1

        # if we need to zero diagonal...
        if zero_diagonal:
            numpy.fill_diagonal(new_cmat,0)

        # return the cmat
        return new_cmat
    
    def node_observations_for_key(self, key, include_info=True, node_name_key=None):
        """Return record for a given key in the form of a dictionary.

        Inputs::

          key: key for which to export - key must contain no more than
               a single value for each edge

          include_info: (Boolean) should export include info

          node_name_key: if provided, will use information stored in
                         the node key, to label nodes, if not
                         provided, will use node labels
        
        """
        try:
            if include_info:
                try:
                    from copy import copy
                    data = copy(self.graph['info'])
                except KeyError:
                    print "No global info found for connectome."
                    data = dict()
                except Exception, e:
                    print e
            else:
                data = dict()
                # for every edge, get data and put in result
            for a in self.nodes_iter():
                if node_name_key is not None:
                    # get node names
                    node_name = self.node[a][node_name_key]
                else:
                    node_name = a
                data[node_name] = self.node[a][key]
            return data
        except Exception, e:
            print e
            return None
        
    def get_info(self):
        """Return connectome info if any."""
        try:
            return self.graph['info']
        except KeyError:
            print "Connectome contains no associated info."
            return None
        except Exception, e:
            print e
            return None
            
    def populate_hagmann_density(self, WM_img, ROI_img):
        """Populate hagmann density."""

        def inverse_sum(elements):
            inverse_elements = []
            for element in elements:
                inverse_elements.append( 1.0 / element )
            from math import fsum
            return fsum(inverse_elements)

        # get surface areas for ROIs
        import images
        surface_area = images.surface_area_for_rois(ROI_img, WM_img)
        # make sure our surface areas are well formed, this means an
        # entry for every key
        epsilon = 0.00000000001
        for n in self.nodes():
            try:
                surface_area[n]
            except KeyError:
                surface_area[n] = epsilon
            except Exception as e:
                raise e
                
        # for every edge...
        for i,j in self.edges_iter():
            calc_hd = ( ( 2.0 / ( surface_area[i] + surface_area[j] ) ) * \
                        inverse_sum( self[i][j]['streamlines_length'] ) )
            self[i][j]['hagmann_density'] = calc_hd

    def populate_node_info(self, ROI_img_data, node_info_file):
        """Populate node information such as ROI name and center of
        mass in the given connectome.

        Inputs::
        
          ROI_img - the ROI image data (as numpy ndarray) from which
                    the connectome was generated. We will use this to
                    generate centers of mass.
          node_info_file - a graphml file which contains node
                           information

        """
        import numpy as np
        # read node info file
        try:
            node_info = networkx.read_graphml(node_info_file)
        except:
            print "Could not read node_info_file!"
            return
        # add node information
        for label, data in node_info.nodes_iter(data=True):
            self.add_node(int(label), data)
            self.node[int(label)]['subject_position'] = tuple( np.mean ( np.where ( ROI_img_data == int(label) ), axis=1 ) )

    def remap(self, mapping):
        """Remap values in connectome acording to map. 

        Inputs::

          mapping: a dictionary containing node keys and the mapping
                   for the corresponding node key, in this form each
                   node key must be represented (bi-directionality is
                   *not* assumed). For (a,b) and (c,d), where {a:c,
                   b:d} and the bi-directional entries do not exist in
                   the mapping, the original entries are removed in
                   both the origin and destination nodes
        
        Example: bi-directionally swap nodes (1,4) and (2,3)
        -------
        >>> mapping = {1:4, 4:1, 2:3, 3:2}
        >>> connectome.remap(mapping)

        """
        touched_list = [] # we need to maintain a list of edges that
                          # we have already touched so that we avoid
                          # swapping edges more than once

        def is_bidirectional(u0,v0):
            # is bidirectional if bidirectional entry exists in
            # mapping, and both edges exist in graph
            both_keys_exist = u0 in mapping.keys() and v0 in mapping.keys()
            if both_keys_exist:
                bidirectional = mapping[u0]==v0 and mapping[v0]==u0
            u1,v1 = remapped_node_keys(u0,v0)
            both_edges_exist = self.has_edge(u1,v1)
            return both_keys_exist and both_edges_exist and bidirectional
            
        def needs_remapping(u0,v0):
            # we need to remap if either u0 or v0 appear anywhere in
            # the mapping... as long as we have not already remapped
            # this edge
            already_visited = (u0,v0) in touched_list
            keys = mapping.keys()
            mapping_entry_found = u0 in keys or v0 in keys
            return not already_visited and mapping_entry_found
            
        def remapped_node_keys(u0,v0):
            return mapping[u0], mapping[v0]

        def shift(u0,v0):
            u1,v1 = remapped_node_keys(u0,v0)
            # try to remove the target edge, this will fail if it does
            # not exist
            try:
                self.remove_edge(u1,v1)
            except:
                pass
            self.add_edge(u1,v1,self[u0][v0]) # add new edge
            self.remove_edge(u0,v0)           # remove old edge
            touched_list.append((u1,v1))      # mark target edge as
                                              # touched

        def swap(u0,v0):
            u1,v1 = remapped_node_keys(u0,v0)
            a = self[u0][v0]
            b = self[u1][v1]
            self.remove_edge(u0,v0)              # remove both edges
            self.remove_edge(u1,v1)
            self.add_edge(u0,v0,b)               # create both edges anew
            self.add_edge(u1,v1,a)
            touched_list.append((u0,v0),(u1,v1)) # mark both edges as
                                                 # touched
            
        for u0,v0 in self.edges():
            if not needs_remapping(u0,v0):
                continue
            if is_bidirectional(u0,v0):
                swap(u0,v0)
            else:
                shift(u0,v0)
            
    def set_info(self, info):
        """Set info for connectome. This will add a info dictionary
        and provided keys/values to the connectome.

        Inputs::

          info: a dictionary containing info to be stored

        """
        self.graph['info'] = info

    def submatrix_for_key(self, submatrix_nodes, key):
        """Return a NxN matrix for key, where N ==
        len(submatrix_nodes). Submatrix nodes are first sorted, then
        metrics are extracted for each edge (i,j) in order according
        to sort.

        """
        import numpy
        submatrix_nodes.sort()        
        n = len(submatrix_nodes)
        new_cmat = numpy.zeros((n,n))
        for i in range(0,n):
            for j in range(0,n):
                node0 = submatrix_nodes[i]
                node1 = submatrix_nodes[j]
                if node0 == node1:
                    new_cmat[i][j] = 0
                else:
                    try:
                        new_cmat[i][j] = self[node0][node1][key]
                    except KeyError:
                        pass
                    except Exception, e:
                        raise e
        return new_cmat

    def write(self, filename):
        """Write connectome to the given filename as gpickle.

        Inputs::

          filename - path at which to save output
        
        """
        try:
            networkx.write_gpickle(self, filename)
        except Exception, e:
            print e
        
    def write_fibers(self, filename):
        """Write fibers as trackvis file to the give filename.

        Inputs::

          filename - path at which to save output
        
        """
        try:
            streamlines = []
            for i,j in self.edges_iter():
                for streamline in self[i][j]['streamlines']:
                    streamlines.append(streamline)
            from nibabel.trackvis import TrackvisFile
            TrackvisFile(streamlines).to_file(filename)
        except Exception, e:
            print e

# MODULE LEVEL FUNCTIONS
def add_info_to_connectomes_from_csv(connectomes,
                                     csvfile,
                                     id_key,
                                     new_filename=None):
    """Add info extracted from a well-formed csv file to the given
    connectomes. Connectomes are provided in the form of a dictionary

    Example
    -------
    >>> import muscip.connectome
    >>> connectomes = {'SUB001': 'SUB001/results/connectome.pkl',
    >>>                'SUB002': 'SUB002/results/connectome.pkl' }
    >>> muscip.connectome.add_info_to_connectomes_from_csv(connectomes,
    >>>                                                    'my_infofile.csv',
    >>>                                                    'Subject_ID')

    Input::

      connectome: a dictionary where the key corresponds to the
      subject id in the csv file, and the value is the path at which
      the subject's connectome file is found

      csvfile: path to csv file which contains clinical info for connectomes

      id_key: string matching the header under which subject id will
      be found in the csv file

      new_filename: (optional) name of new connectome - if none is
      provided, will overwrite existing connectome file.

    """
    import os.path as op
    from copy import copy
    # create the csv reader and grab data
    try:
        import csv
        read_info = dict()
        f = open(op.abspath(csvfile), 'rt')
        reader = csv.DictReader(f)
        for record in reader:
            read_info[record[id_key]] = record
    except Exception, e:
        print e
    finally:
        f.close()
    # for every connectome entry, try and get info from the info we
    # previously read
    for C_id in connectomes.keys():
        # try to get record from read info
        try:
            new_info = read_info[C_id]
        except KeyError:
            print "No info found in csv file for: %s" % C_id
            continue
        # try to read connectome file and return as copy of itself
        try:
            C_path = op.abspath(connectomes[C_id])
            C_dir = op.dirname(C_path)
            C = copy(read_gpickle(C_path))
        except Exception, e:
            print "Could not read connectome file -- %s" % e
            continue
        # set new info
        C.set_info(new_info)
        # try to save connectome
        try:
            if new_filename:
                C.write(op.join(C_dir, new_filename))
            else:
                C.write(C_path)
        except Exception, e:
            print "Could not save connectome file -- %s" % e
            
def edge_data_for_connectomes_as_df(C_list, edge_data_key, filename,
                                    include_info=True, node_name_key=None):
    """Write data frame as csv file to the given path.

    Inputs::

      C_list: list of connectome paths
      edge_data_key: extract values belonging to this key
      filename: write file to this path
      include_info: (Boolean) include info?; default=True
      node_name_key: if provided, use this key to extract node names
    
    """
    # get the union of all keys, we need this to be all inclusive
    all_info_keys = list()
    all_data_keys = list()
    for C_path in C_list:
        C = read_gpickle(C_path)
        if include_info:
            # add any info keys not yet in union
            try:
                for k in C.graph['info'].keys():
                    if k not in all_info_keys:
                        all_info_keys.append(k)
            except KeyError:
                print "Info requested, but no info exists in Connectome."
            except Exception, e:
                print e
        # add every edge key we find
        try:
            c_keys = C.edge_observations_for_key(edge_data_key,
                                                 include_info=False,
                                                 node_name_key=node_name_key).keys()
            for k in c_keys:
                if k not in all_data_keys:
                    all_data_keys.append(k)
        except Exception, e:
            print e
    all_info_keys.sort()
    all_data_keys.sort()
    all_keys = all_info_keys + all_data_keys
    print all_keys
    # export to csv file ~~~~~~~~~~~~~~~~~~~
    try:
        import csv
        import os.path as op
        fout = open(op.abspath(filename), 'wt')
        writer = csv.DictWriter(fout, fieldnames=all_keys)
        header = dict( (k,k) for k in all_keys)
        writer.writerow(header)
        for C_path in C_list:
            C = read_gpickle(C_path)
            data = C.edge_observations_for_key(edge_data_key,
                                               include_info=include_info,
                                               node_name_key=node_name_key)
            writer.writerow(data)
    except Exception, e:
        print e
    finally:
        fout.close()
    
def generate_connectome(fib, roi_img, node_info=None):
    """Return a TNConnectome object

    Example
    -------
    import tn_image_processing as tnip
    import nibabel
    fibers = tnip.fibers.read('path/to/track.trk')
    roi = nibabel.load('path/to/roi.nii.gz')
    C = tnip.connectome.generate_connectome(fibers, roi)

    Input::

      [mandatory]
      fibers - a loaded fiber object from
               tn_image_processing.fibers
      roi_img - a loaded nibabel image

    """
    import os, fibers

    # create connectome object and store initializing properties
    connectome = TNConnectome()
    connectome.graph['roi_img'] = os.path.abspath(roi_img.get_filename())
    # get ROI data
    roi_data = roi_img.get_data()
    # load node info if provided
    if node_info:
        connectome.populate_node_info(roi_data, node_info)
    # get our vertex key - we will use voxel spacing to determine
    # intersection of ROIs, we are assuming that ROI atlas is in same
    # space as diffusion, as is best practice
    vertex_key = 'vertices_vox'
    # TODO: should write an interater so that we don't need to load
    # all of this into memory
    streamlines = fib.get_data()
    for streamline in streamlines:
        # get the endpoints of streamline in terms of voxel indices
        vertex_i = streamlines[streamline][vertex_key][0]
        vertex_j = streamlines[streamline][vertex_key][-1]
        voxel_i = [int(vertex_i[0]), int(vertex_i[1]),
                   int(vertex_i[2])]
        voxel_j = [int(vertex_j[0]), int(vertex_j[1]),
                   int(vertex_j[2])]
        # try and get value for voxel indices from roi data (it is
        # possible that we are outside of the bounds of the ROI, due
        # to the propegation of the tracks beyond the bounds of ROI
        # image in tracking)
        try:
            label_i = int(roi_data[tuple(voxel_i)])
            label_j = int(roi_data[tuple(voxel_j)])
        except IndexError:
            continue
        # if both endpoints reside in ROIs (both endpoints are
        # non-zero)...
        if label_i != 0 and label_j != 0:
            # ...then we need to add to the fiber count for the
            # specified edge
            try:
                connectome[label_i][label_j]['number_of_fibers'] += 1
                connectome[label_i][label_j]['streamlines'].append(streamline)
                connectome[label_i][label_j]['streamlines_length'].append(
                    fibers.length_of_streamline(streamlines[streamline], vox_dims=fib.get_voxel_size()))
            # handle the case where the edge does not yet exist
            except KeyError:
                connectome.add_edge(label_i, label_j)
                connectome[label_i][label_j]['number_of_fibers'] = 1
                connectome[label_i][label_j]['streamlines'] = [streamline]
                connectome[label_i][label_j]['streamlines_length'] = \
                    [fibers.length_of_streamline(streamlines[streamline], vox_dims=fib.get_voxel_size())]

    # calculate and store mean fiber lengths and std
    import numpy
    for i,j in connectome.edges_iter():
        connectome[i][j]['fiber_length_mean'] = numpy.asarray(connectome[i][j]['streamlines_length']).mean()
        connectome[i][j]['fiber_length_std'] = numpy.asarray(connectome[i][j]['streamlines_length']).std()

    # return our results
    return connectome

def generate_connectome_from_cmat(cmat,
                                  metric_key,
                                  roi_img = None,
                                  node_info = None):
    """Return a TNConnectome object

    Example
    -------
    import muscip.connectome as mcon
    C = mcon.connectome.generate_connectome_from_cmat(cmat, 'my_new_key')

    Input::

    [mandatory]

      cmat - connection matrix indicating some metric

      metric_key - key under which to store metric

    [optional]

      roi_img - a loaded nibabel image representing rois

      node_info - node information

    """
    C = TNConnectome()
    if roi_img is not None and node_info is not None:
        C.populate_node_info(roi_img.get_data(), node_info)
    for i in range(0,cmat.shape[0]):
        for j in range(0,cmat.shape[1]):
            C.add_edge(i,j)
            C[i][j][metric_key] = (cmat[i,j] + cmat[j,i]) / 2.0
    return C
    
def read_gpickle(filename):
    """Create connectome object from a given gpickle.

    Input::

      filename - path to networkx gpickle file
    """
    read_graph = networkx.read_gpickle(filename)
    connectome = TNConnectome()
    connectome.graph = read_graph.graph
    for i,data in read_graph.nodes_iter(data=True):
        connectome.add_node(i,data)
    for i,j,data in read_graph.edges_iter(data=True):
        connectome.add_edge(i,j,data)
    return connectome