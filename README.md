# atlas

**atlas** is a Python GUI application designed for viewing FITS files using the Model-View-ViewModel (MVVM) architectural pattern. While currently focused on FITS files, the framework is designed to be extendable for other file types and applications in the future.

## Project Structure

The project is organized as follows:

- **`src/main.py`**: Entry point of the application.
- **`src/model`**: Contains the data model.
- **`src/view`**: Implements the main GUI for viewing.
- **`src/viewmodel`**: Manages the interaction between the model and the view.

## Requirements

This project requires Python 3.10 or higher and the following Python packages:

- `astropy`
- `numpy`
- `PyQt5`
- `matplotlib`

You can install the required packages using the `requirements.txt` file:

```sh
pip install -r requirements.txt
```

## Usage

To run the application, use the following command:

```sh
python src/main.py
```

## Reporting Issues

If you encounter any problems or have questions about this project, please open an issue on the [GitHub Issues page](https://github.com/CaltechOpticalObservatories/atlas/issues). Your feedback helps us improve the project!
