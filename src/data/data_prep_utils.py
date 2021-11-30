from pathlib import Path
import scipy.io as sio
import numpy as np
import pandas as pd

###############################################################################
# Helper functions
###############################################################################


def set_directories():
    """Sets the directory paths used for data, checkpoints, etc."""

    # check if "scratch" path exists in the home directory
    # if it does, assume we are on HPC
    scratch_path = Path.home() / "scratch"
    if scratch_path.exists():
        print("Assume on HPC")
    else:
        print("Assume on local compute")

    path_processed_data = Path(args.path_data)

    # if loading the model from a checkpoint, a checkpoint folder name
    # should be passed as an argument, like: -c 2021_07_14_185903
    # the various .pt files will be inside the checkpoint folder
    if args.ckpt_name:
        prev_checkpoint_folder_name = args.ckpt_name
    else:
        # set dummy name for path_prev_checkpoint
        path_prev_checkpoint = Path("no_prev_checkpoint_needed")

    if args.proj_dir:
        proj_dir = Path(args.proj_dir)
    else:
        # proj_dir assumed to be cwd
        proj_dir = Path.cwd()

    # set time
    if args.model_time_suffix:
        model_start_time = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S") + "_" + args.model_time_suffix
    else:
        model_start_time = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")

    if scratch_path.exists():
        # for HPC
        root_dir = scratch_path / "earth-mantle-surrogate"
        print(root_dir)

        if args.ckpt_name:
            path_prev_checkpoint = (
                root_dir / "models/interim/checkpoints" / prev_checkpoint_folder_name
            )
            if Path(path_prev_checkpoint).exists():
                print(
                    "Previous checkpoints exist. Training from most recent checkpoint."
                )

                path_prev_checkpoint = find_most_recent_checkpoint(path_prev_checkpoint)

            else:
                print(
                    "Could not find previous checkpoint folder. Training from beginning."
                )

        path_input_folder = path_processed_data / "input"
        path_truth_folder = path_processed_data / "truth"
        path_checkpoint_folder = (
            root_dir / "models/interim/checkpoints" / model_start_time
        )
        Path(path_checkpoint_folder).mkdir(parents=True, exist_ok=True)

    else:

        # for local compute
        root_dir = Path.cwd()  # set the root directory as a Pathlib path
        print(root_dir)

        if args.ckpt_name:
            path_prev_checkpoint = (
                root_dir / "models/interim/checkpoints" / prev_checkpoint_folder_name
            )
            if Path(path_prev_checkpoint).exists():
                print(
                    "Previous checkpoints exist. Training from most recent checkpoint."
                )

                path_prev_checkpoint = find_most_recent_checkpoint(path_prev_checkpoint)

            else:
                print(
                    "Could not find previous checkpoint folder. Training from beginning."
                )

        path_input_folder = path_processed_data / "input"
        path_truth_folder = path_processed_data / "truth"
        path_checkpoint_folder = (
            root_dir / "models/interim/checkpoints" / model_start_time
        )
        Path(path_checkpoint_folder).mkdir(parents=True, exist_ok=True)

    # save src directory as a zip into the checkpoint folder
    shutil.make_archive(
        path_checkpoint_folder / f"src_files_{model_start_time}",
        "zip",
        proj_dir / "src",
    )
    shutil.copy(
        proj_dir / "bash_scripts/train_model_hpc.sh",
        path_checkpoint_folder / "train_model_hpc.sh",
    )

    return (
        root_dir,
        path_input_folder,
        path_truth_folder,
        path_checkpoint_folder,
        path_prev_checkpoint,
        model_start_time,
    )



###############################################################################
# Data Prep Classes
###############################################################################


class MillingDataPrep:
    def __init__(
        self,
        path_raw_data,
        path_df_labels=None,
        window_size=64,
        stride=64,
        cut_drop_list=[17, 94],
    ):
        """Prepare the UC Berkeley Milling dataset for training.

        Parameters
        ----------
        path_raw_data : pathlib
            Path to the raw data folder. Should point to a 'mill.mat' or similar file.

        path_df_labels : pathlib, optional
            Path to the dataframe with the labels. If not provided, the dataframe must be created.

        window_size : int
            Size of the window to be used for the sliding window.

        stride : int
            Size of the stride to be used for the sliding window.

        cut_drop_list : list
            List of cut numbers to be dropped from the dataset. cut_no 17 and 94 are erroneous.

        """

        self.data_file = path_raw_data  # path to the raw data file
        self.window_size = window_size  # size of the window
        self.stride = stride  # stride between windows
        self.cut_drop_list = cut_drop_list  # list of cut numbers to be dropped

        assert (self.data_file.exists()), "mill.mat does not exist or is not extracted from zip"
        assert (self.window_size > 0 ), "window_size must be greater than 0"
        assert (self.stride > 0), "stride must be greater than 0"


        if path_df_labels is None:
            print("Warning: no csv defined for creating labels. Create one.")
        else:
            self.df_labels = pd.read_csv(path_df_labels) # path to the labels file with tool class
            if self.cut_drop_list is not None:
                self.df_labels.drop(self.cut_drop_list, inplace=True) # drop the cuts that are bad

            self.df_labels.reset_index(drop=True, inplace=True) # reset the index

        # load the data from the matlab file
        m = sio.loadmat(self.data_file, struct_as_record=True)

        # store the 'mill' data in a seperate np array
        self.data = m["mill"]

        self.field_names = self.data.dtype.names
        self.signal_names = self.field_names[7:][::-1]

    def create_labels(self):
        """Function that will create the label dataframe from the mill data set

        Only needed if the dataframe with the labels is not provided.
        """

        # create empty dataframe for the labels
        df_labels = pd.DataFrame()

        # get the labels from the original .mat file and put in dataframe
        for i in range(7):
            # list for storing the label data for each field
            x = []

            # iterate through each of the unique cuts
            for j in range(167):
                x.append(self.data[0, j][i][0][0])
            x = np.array(x)
            df_labels[str(i)] = x

        # add column names to the dataframe
        df_labels.columns = self.field_names[0:7]

        # create a column with the unique cut number
        df_labels["cut_no"] = [i for i in range(167)]

        def tool_state(cols):
            """Add the label to the cut.

            Categories are:
            Healthy Sate (label=0): 0~0.2mm flank wear
            Degredation State (label=1): 0.2~0.7mm flank wear
            Failure State (label=2): >0.7mm flank wear
            """
            # pass in the tool wear, VB, column
            vb = cols

            if vb < 0.2:
                return 0
            elif vb >= 0.2 and vb < 0.7:
                return 1
            elif pd.isnull(vb):
                pass
            else:
                return 2

        # apply the label to the dataframe
        df_labels["tool_class"] = df_labels["VB"].apply(tool_state)

        return df_labels

    def create_data_array(self, cut_no):
        """Create an array from a cut sample.

        Parameters
        ===========
        cut_no : int
            Index of the cut to be used.

        Returns
        ===========
        sub_cut_array : np.array
            Array of the cut samples. Shape of [no. samples, sample len, features/sample]

        sub_cut_labels : np.array
            Array of the labels for the cut samples. Shape of [# samples, # features/sample]

        """

        assert (cut_no in self.df_labels["cut_no"].values), "Cut number must be in the dataframe"

        # create a numpy array of the cut
        # with a final array shape like [no. cuts, len cuts, no. signals]
        cut = self.data[0, cut_no]
        for i, signal_name in enumerate(self.signal_names):
            if i == 0:
                cut_array = cut[signal_name].reshape((9000, 1))
            else:
                cut_array = np.concatenate(
                    (cut_array, cut[signal_name].reshape((9000, 1))), axis=1
                )

        # select the start and end of the cut
        start = self.df_labels[self.df_labels["cut_no"] == cut_no]["window_start"].values[0]
        end = self.df_labels[self.df_labels["cut_no"] == cut_no]["window_end"].values[0]
        cut_array = cut_array[start:end, :]

        # instantiate the "temporary" lists to store the sub-cuts and metadata
        sub_cut_list = []
        sub_cut_id_list = []
        sub_cut_label_list = []

        # get the labels for the cut
        label = self.df_labels[self.df_labels["cut_no"] == cut_no]["tool_class"].values[0]

        # fit the strided windows into the dummy_array until the length
        # of the window does not equal the proper length (better way to do this???)
        for i in range(cut_array.shape[0]):
            windowed_signal = cut_array[
                i * self.stride : i * self.stride + self.window_size
            ]

            # if the windowed signal is the proper length, add it to the list
            if windowed_signal.shape == (self.window_size, 6):
                sub_cut_list.append(windowed_signal)

                # create sub_cut_id fstring to keep track of the cut_id and the window_id
                sub_cut_id_list.append(f"{cut_no}_{i}")

                # create the sub_cut_label and append it to the list
                sub_cut_label_list.append(int(label))

            else:
                break

        sub_cut_array = np.array(sub_cut_list)

        sub_cut_ids = np.expand_dims(np.array(sub_cut_id_list, dtype=str), axis=1)
        sub_cut_ids = np.repeat(sub_cut_ids, sub_cut_array.shape[1], axis=1)

        sub_cut_labels = np.expand_dims(np.array(sub_cut_label_list, dtype=int), axis=1)
        sub_cut_labels = np.repeat(sub_cut_labels, sub_cut_array.shape[1], axis=1)

        # take the length of the signals in the sub_cut_array
        # and divide it by the frequency (250 Hz) to get the time (seconds) of each sub-cut
        sub_cut_times = np.expand_dims(
            np.arange(0, sub_cut_array.shape[1]) / 250.0, axis=0
        )
        sub_cut_times = np.repeat(
            sub_cut_times,
            sub_cut_array.shape[0],
            axis=0,
        )

        sub_cut_labels_ids_times = np.stack(
            (sub_cut_labels, sub_cut_ids, sub_cut_times), axis=2
        )

        return (
            sub_cut_array,
            sub_cut_labels,
            sub_cut_ids,
            sub_cut_times,
            sub_cut_labels_ids_times,
        )

    def create_xy_arrays(self):
        """Create the x and y arrays used in deep learning.

        Returns
        ===========
        x_array : np.array
            Array of the cut samples. Shape of [no. samples, sample len, features/sample]

        y_array : np.array
            Array of the labels for the cut samples. Shape of [no. samples, sample len, label/ids/times]

        """

        # create a list to store the x and y arrays
        x = []  # instantiate X's
        y_labels_ids_times = []  # instantiate y's

        # iterate throught the df_labels
        for i in self.df_labels.itertuples():
            (
                sub_cut_array,
                sub_cut_labels,
                sub_cut_ids,
                sub_cut_times,
                sub_cut_labels_ids_times,
            ) = self.create_data_array(i.cut_no)

            x.append(sub_cut_array)
            y_labels_ids_times.append(sub_cut_labels_ids_times)

        return np.vstack(x), np.vstack(y_labels_ids_times)

    def create_xy_dataframe(self):
        """Create a flat dataframe (2D array) of the x and y arrays.

        Returns
        ===========
        df : pd.DataFrame
            Single flat dataframe containing each sample and its labels.

        """

        x, y_labels_ids_times = self.create_xy_arrays()  # create the x and y arrays

        # concatenate the x and y arrays and reshape them to be a flat array (2D)
        x_labels = np.reshape(np.concatenate((x, y_labels_ids_times), axis=2), (-1, 9))

        # define the column names and the data types
        col_names = [s.lower() for s in list(self.signal_names)] + [
            "tool_class",
            "cut_id",
            "time",
        ]

        col_names_ordered = [
            "cut_id",
            "case",
            "time",
            "ae_spindle",
            "ae_table",
            "vib_spindle",
            "vib_table",
            "smcdc",
            "smcac",
            "tool_class",
        ]

        col_dtype = [
            str,
            int,
            np.float32,
            np.float32,
            np.float32,
            np.float32,
            np.float32,
            np.float32,
            np.float32,
            int,
        ]

        col_dtype_dict = dict(zip(col_names_ordered, col_dtype))

        # create a dataframe from the x and y arrays
        df = pd.DataFrame(x_labels, columns=col_names, dtype=str)

        # split the cut_id by "_" and take the first element (case)
        df["case"] = df["cut_id"].str.split("_").str[0]  

        df = df[col_names_ordered].astype(col_dtype_dict) # reorder the columns

        return df


# skip pronostia data set
# class PronostiaDataPrep():
#     """Parameters
#     ===========
#     folder_raw_data_train : pathlib object 
#         Location of raw training data, likely in ./data/raw/FEMTO/Training_set/Learning_set/

#     folder_raw_data_test : pathlib object """

#     def __init__(self):
#         pass




    
