import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog
from tkinter import ttk
import serial
import serial.tools.list_ports
import subprocess
import os
import threading
import sys
import time
import re  # Import regular expressions module

# Paths to the tools
ARDUINO_CLI_PATH = "arduino-cli"  # Ensure arduino-cli is in your system's PATH
ESPTOOL_PY_PATH = "esptool.py"    # Ensure esptool.py is in your system's PATH

UDEV_RULE_PATH = '/etc/udev/rules.d/99-esp32.rules'  # Path to udev rules file

# Global variables for serial monitor
serial_port = None
monitor_running = False
console_window = None
console_text = None  # Declare console_text at the global scope

# Function to update the progress bar
def update_progress(value):
    progress_bar['value'] = value
    root.update_idletasks()

# Function to update the status label in the main GUI
def update_status_label(message):
    status_label.config(text=message)
    root.update_idletasks()

# Function to update the console window logs
def update_console(message):
    if console_window and console_text:
        console_text.configure(state=tk.NORMAL)
        console_text.insert(tk.END, message + '\n')
        console_text.configure(state=tk.DISABLED)
        console_text.see(tk.END)

# Function to list all available serial ports and check if they have symbolic names and serial numbers
def get_serial_ports():
    ports = list(serial.tools.list_ports.comports())
    available_ports = []
    
    for port in ports:
        serial_number = port.serial_number if port.serial_number else "N/A"
        # Only add ports with valid devices and serial numbers
        if serial_number != "N/A" and port.device:
            symbolic_name = get_symbolic_name_by_serial(serial_number)
            display_name = port.device
            if symbolic_name:
                display_name = f"/dev/{symbolic_name} ({port.device})"
            available_ports.append(f"{display_name} - {port.description} | Serial: {serial_number}")
    
    return available_ports

# Function to get symbolic name of a port by serial number from the udev rules
def get_symbolic_name_by_serial(serial_number):
    if os.path.exists(UDEV_RULE_PATH):
        with open(UDEV_RULE_PATH, 'r') as f:
            rules = f.readlines()
        
        # Loop through all the udev rules
        for rule in rules:
            # Check if the serial number is in the rule and the rule contains SYMLINK
            if serial_number in rule and 'SYMLINK+=' in rule:
                # Extract the symbolic name between the quotes after SYMLINK+=
                symbolic_name = rule.split('SYMLINK+="')[1].split('"')[0]
                return symbolic_name
    return None

# Function to onboard a selected port with a custom symbolic name
def onboard_port():
    selected_port = dropdown.get()
    if not selected_port:
        messagebox.showerror("Error", "Please select a port.")
        return
    port_device = selected_port.split(" - ")[0].split(" ")[0]
    serial_number = selected_port.split("Serial: ")[1]  # Extract serial number
    custom_name = simpledialog.askstring("Onboard Port", f"Enter the custom name for the port with serial {serial_number}:")
    
    if serial_number and custom_name:
        rule = f'SUBSYSTEM=="tty", ATTRS{{serial}}=="{serial_number}", SYMLINK+="{custom_name}"\n'
        
        # Append the new rule to the file
        with open(UDEV_RULE_PATH, 'a') as f:
            f.write(rule)
        
        reload_udev_rules()
        messagebox.showinfo("Success", f"Port with serial {serial_number} onboarded with name: {custom_name}")
        refresh_ports()

# Function to replace a port's serial number in an existing symbolic name
def replace_serial_in_symbolic_name():
    selected_port = dropdown.get()
    if not selected_port:
        messagebox.showerror("Error", "Please select a port.")
        return
    serial_number = selected_port.split("Serial: ")[1]  # Extract serial number
    existing_symbolic_name = get_symbolic_name_by_serial(serial_number)
    
    if not existing_symbolic_name:
        messagebox.showerror("Error", f"No symbolic name found for the port with serial {serial_number}.")
        return
    
    new_port_serial = simpledialog.askstring("Replace Serial", f"Enter the new port's serial number to map to '{existing_symbolic_name}':")
    
    if new_port_serial:
        replaced = False
        if os.path.exists(UDEV_RULE_PATH):
            with open(UDEV_RULE_PATH, 'r') as f:
                rules = f.readlines()
            
            # Replace the old serial number with the new one in the matching rule
            with open(UDEV_RULE_PATH, 'w') as f:
                for rule in rules:
                    if existing_symbolic_name in rule and 'SYMLINK+=' in rule:
                        rule = rule.split('ATTRS{serial}')[0] + f'ATTRS{{serial}}=="{new_port_serial}", SYMLINK+="{existing_symbolic_name}"\n'
                        replaced = True
                    f.write(rule)
        
        if replaced:
            reload_udev_rules()
            messagebox.showinfo("Success", f"Symbolic name '{existing_symbolic_name}' now maps to serial {new_port_serial}.")
            refresh_ports()
        else:
            messagebox.showerror("Error", f"Failed to replace the serial for '{existing_symbolic_name}'.")

# Function to rename a symbolic name for an existing serial number
def rename_symbolic_name():
    selected_port = dropdown.get()
    if not selected_port:
        messagebox.showerror("Error", "Please select a port.")
        return
    serial_number = selected_port.split("Serial: ")[1]  # Extract serial number
    existing_symbolic_name = get_symbolic_name_by_serial(serial_number)
    
    if not existing_symbolic_name:
        messagebox.showerror("Error", f"No symbolic name found for the port with serial {serial_number}.")
        return
    
    new_symbolic_name = simpledialog.askstring("Rename Symbolic Name", f"Enter the new symbolic name for serial {serial_number}:")
    
    if new_symbolic_name and existing_symbolic_name:
        renamed = False
        if os.path.exists(UDEV_RULE_PATH):
            with open(UDEV_RULE_PATH, 'r') as f:
                rules = f.readlines()
            
            # Rename the symbolic name in the matching rule
            with open(UDEV_RULE_PATH, 'w') as f:
                for rule in rules:
                    if existing_symbolic_name in rule and 'SYMLINK+=' in rule:
                        rule = rule.replace(f'SYMLINK+="{existing_symbolic_name}"', f'SYMLINK+="{new_symbolic_name}"')
                        renamed = True
                    f.write(rule)
            
        if renamed:
            reload_udev_rules()
            messagebox.showinfo("Success", f"Symbolic name '{existing_symbolic_name}' renamed to '{new_symbolic_name}'.")
            refresh_ports()
        else:
            messagebox.showerror("Error", f"Failed to rename '{existing_symbolic_name}'.")

# Function to delete a symbolic name rule
def delete_symbolic_name():
    selected_port = dropdown.get()
    if not selected_port:
        messagebox.showerror("Error", "Please select a port.")
        return
    serial_number = selected_port.split("Serial: ")[1]  # Extract serial number
    symbolic_name = get_symbolic_name_by_serial(serial_number)
    
    if not symbolic_name:
        messagebox.showerror("Error", f"No symbolic name found for the port with serial {serial_number}.")
        return
    
    deleted = False
    if os.path.exists(UDEV_RULE_PATH):
        with open(UDEV_RULE_PATH, 'r') as f:
            rules = f.readlines()
        
        # Remove the matching rule from the file
        with open(UDEV_RULE_PATH, 'w') as f:
            for rule in rules:
                if symbolic_name not in rule:
                    f.write(rule)
                else:
                    deleted = True
    
    if deleted:
        reload_udev_rules()
        messagebox.showinfo("Success", f"Symbolic name '{symbolic_name}' has been deleted.")
        refresh_ports()
    else:
        messagebox.showerror("Error", f"Symbolic name '{symbolic_name}' not found.")

# Function to reload udev rules
def reload_udev_rules():
    try:
        subprocess.run(['sudo', 'udevadm', 'control', '--reload-rules'], check=True)
        subprocess.run(['sudo', 'udevadm', 'trigger'], check=True)
    except subprocess.CalledProcessError as e:
        messagebox.showerror("Error", f"Failed to reload udev rules: {e}")

# Function to refresh the list of ports
def refresh_ports():
    available_ports = get_serial_ports()
    dropdown['values'] = available_ports
    if available_ports:
        dropdown.current(0)
    else:
        dropdown.set("No available ports found")

# Function to compile the selected Arduino code
def compile_code(sketch_path):
    try:
        update_status_label("Compiling...")
        update_console("Compiling Arduino code...")
        process = subprocess.Popen(
            [
                ARDUINO_CLI_PATH,
                "compile",
                "--fqbn", "esp32:esp32:esp32doit-devkit-v1",
                "--board-options", "UploadSpeed=115200",
                "--verbose",
                sketch_path
            ],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        total_steps = 20  # Estimate total number of steps
        current_step = 0

        for line in process.stdout:
            update_console(line.strip())
            # Update progress based on specific output patterns
            if "Compiling sketch..." in line:
                current_step = 2
            elif "Compiling libraries..." in line:
                current_step = 4
            elif "Compiling core..." in line:
                current_step = 6
            elif "Linking everything together..." in line:
                current_step = 8
            elif "Building..." in line:
                current_step += 1
            elif "Sketch uses" in line:
                current_step = total_steps - 1  # Almost done
            # Calculate progress percentage
            progress = int((current_step / total_steps) * 100)
            update_progress(progress)
            # Update status label with the last line
            update_status_label(line.strip())

        process.wait()
        if process.returncode == 0:
            update_progress(100)
            update_console("Compilation successful.")
            update_status_label("Compilation successful.")
            return True
        else:
            update_console("Compilation failed.")
            update_status_label("Compilation failed.")
            messagebox.showerror("Compilation Error", "Compilation failed. Check logs for details.")
            return False
    except Exception as e:
        update_console(f"Error during compilation: {e}")
        update_status_label("Error during compilation.")
        messagebox.showerror("Error", f"Error during compilation:\n{e}")
        return False

# Function to upload the compiled code to the selected port
def upload_code(port, sketch_path):
    try:
        update_status_label("Uploading...")
        update_console(f"Uploading code to {port}...")
        process = subprocess.Popen(
            [
                ARDUINO_CLI_PATH,
                "upload",
                "-p", port,
                "--fqbn", "esp32:esp32:esp32doit-devkit-v1",
                "--board-options", "UploadSpeed=115200",
                sketch_path,
                "--verbose"
            ],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )

        total_steps = 10  # Estimate total number of steps
        current_step = 0

        for line in process.stdout:
            update_console(line.strip())
            # Update progress based on specific output patterns
            if "Connecting..." in line:
                current_step = 2
            elif "Chip is" in line:
                current_step = 4
            elif "Writing at" in line:
                current_step += 1
            elif "Hash of data verified" in line:
                current_step = total_steps - 1
            # Calculate progress percentage
            progress = int((current_step / total_steps) * 100)
            update_progress(progress)
            # Update status label with the last line
            update_status_label(line.strip())

        process.wait()
        if process.returncode == 0:
            update_progress(100)
            update_console("Upload successful.")
            update_status_label("Upload successful.")
            messagebox.showinfo("Success", "Code uploaded successfully!")
        else:
            update_console(f"Upload failed with exit status {process.returncode}.")
            update_status_label("Upload failed.")
            messagebox.showerror("Upload Error", f"Upload failed. Check logs for details.")
    except Exception as e:
        update_console(f"Error during upload: {e}")
        update_status_label("Error during upload.")
        messagebox.showerror("Error", f"Error during upload:\n{e}")

# Function to upload the binary file to the selected port
def upload_binary(port, bin_path):
    try:
        update_status_label("Uploading binary...")
        update_console(f"Uploading binary to {port}...")

        cmd = [
            ESPTOOL_PY_PATH,
            "--chip", "esp32",
            "--port", port,
            "--baud", "115200",
            "write_flash", "-z",
            "--flash_mode", "dio",
            "--flash_freq", "40m",
            "--flash_size", "detect",
            "0x1000", bin_path
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )

        total_steps = 10  # Estimate total number of steps
        current_step = 0

        for line in process.stdout:
            update_console(line.strip())
            # Update progress based on specific output patterns
            if "Connecting..." in line:
                current_step = 2
            elif "Chip is" in line:
                current_step = 4
            elif "Writing at" in line:
                current_step += 1
            elif "Hash of data verified" in line:
                current_step = total_steps - 1
            # Calculate progress percentage
            progress = int((current_step / total_steps) * 100)
            update_progress(progress)
            # Update status label with the last line
            update_status_label(line.strip())

        process.wait()
        if process.returncode == 0:
            update_progress(100)
            update_console("Binary upload successful.")
            update_status_label("Upload successful.")
            messagebox.showinfo("Success", "Binary uploaded successfully!")
        else:
            update_console(f"Upload failed with exit status {process.returncode}.")
            update_status_label("Upload failed.")
            messagebox.showerror("Upload Error", f"Upload failed. Check logs for details.")
    except Exception as e:
        update_console(f"Error during upload: {e}")
        update_status_label("Error during upload.")
        messagebox.showerror("Error", f"Error during upload:\n{e}")

# Function to compile and upload the code to the selected serial port
def compile_and_upload():
    selected_port = dropdown.get()
    if not selected_port:
        messagebox.showerror("Error", "Please select a port.")
        return
    port_device = selected_port.split(" - ")[0].split(" ")[0]
    file_path = file_path_var.get()

    if not file_path:
        messagebox.showerror("Error", "Please select a file.")
        return

    # Disable button while compiling/uploading
    upload_button.config(state=tk.DISABLED)

    # Update progress bar and reset
    update_progress(0)
    update_status_label("")

    # Stop serial monitor during upload
    stop_serial_monitor()

    # Determine if the file is .ino or .bin
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    # Run the compilation and upload in a separate thread
    def task():
        if ext == '.ino':
            # Compile and upload using arduino-cli
            if compile_code(file_path):
                upload_code(port_device, file_path)
        elif ext == '.bin':
            # Upload directly using esptool.py
            upload_binary(port_device, file_path)
        else:
            messagebox.showerror("Error", "Unsupported file type. Please select a .ino or .bin file.")
            update_status_label("Unsupported file type.")

        # Re-enable the button after the process is complete
        upload_button.config(state=tk.NORMAL)

        # Restart serial monitor after upload
        start_serial_monitor(port_device)

    threading.Thread(target=task).start()

# Function to browse for a file (either .ino or .bin)
def browse_file():
    filename = filedialog.askopenfilename(
        title="Select File",
        filetypes=[("Arduino Sketch or Binary", "*.ino *.bin")]
    )
    file_path_var.set(filename)

# Function to open the console window
def open_console_window():
    global console_window, console_text  # Declare console_text as global
    if console_window:
        console_window.deiconify()
        return

    console_window = tk.Toplevel(root)
    console_window.title("Console and Serial Monitor")
    console_window.geometry("800x400")

    console_text = tk.Text(console_window, height=25, state=tk.DISABLED, wrap=tk.WORD)
    console_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

    # Start serial monitor if port is selected
    selected_port = dropdown.get()
    if selected_port:
        port_device = selected_port.split(" - ")[0].split(" ")[0]
        start_serial_monitor(port_device)

    # Handle console window close event
    console_window.protocol("WM_DELETE_WINDOW", on_console_close)

# Function to handle console window close event
def on_console_close():
    global console_window
    stop_serial_monitor()
    console_window.destroy()
    console_window = None

# Function to start serial monitor
def start_serial_monitor(port):
    global serial_port, monitor_running
    if monitor_running:
        return
    try:
        serial_port = serial.Serial(port, baudrate=115200, timeout=1)
        monitor_running = True
        threading.Thread(target=read_from_port, daemon=True).start()
        update_console(f"Serial monitor started on {port}")
    except serial.SerialException as e:
        update_console(f"Error opening serial port {port}: {e}")
        monitor_running = False

# Function to stop serial monitor
def stop_serial_monitor():
    global serial_port, monitor_running
    monitor_running = False
    if serial_port and serial_port.is_open:
        serial_port.close()
        update_console("Serial monitor stopped")
        serial_port = None

# Function to read from serial port
def read_from_port():
    global serial_port, monitor_running
    while monitor_running and serial_port and serial_port.is_open:
        try:
            line = serial_port.readline().decode('utf-8', errors='replace').rstrip()
            if line:
                update_console(line)
        except Exception as e:
            update_console(f"Error reading from serial port: {e}")
            break
    monitor_running = False

# GUI Setup
root = tk.Tk()
root.title("Dognosis Port Manager")

# Set window size
root.geometry("800x700")

# Frame for branding and app title
branding_frame = ttk.Frame(root)
branding_frame.pack(fill=tk.X, pady=10)

title_label = ttk.Label(branding_frame, text="Dognosis Serial Port Manager", font=("Helvetica", 18, "bold"), anchor="center")
title_label.pack()

# Main frame for the app content
frame = ttk.Frame(root)
frame.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)

# Label for dropdown
ttk.Label(frame, text="Select a Serial Port:", font=("Helvetica", 12)).pack(pady=5)

# Dropdown for available serial ports
available_ports = get_serial_ports()
selected_port_var = tk.StringVar()

dropdown = ttk.Combobox(frame, textvariable=selected_port_var, values=available_ports, state="readonly", font=("Helvetica", 10), width=80)
dropdown.pack(pady=10, fill=tk.X)
if available_ports:
    dropdown.current(0)
else:
    dropdown.set("No available ports found")

# Buttons for Port Manager actions
button_frame = ttk.Frame(frame)
button_frame.pack(pady=10)

ttk.Button(button_frame, text="Onboard Selected Port", command=onboard_port, width=30).pack(pady=5)
ttk.Button(button_frame, text="Replace Serial in Symbolic Name", command=replace_serial_in_symbolic_name, width=30).pack(pady=5)
ttk.Button(button_frame, text="Rename Symbolic Name", command=rename_symbolic_name, width=30).pack(pady=5)
ttk.Button(button_frame, text="Delete Symbolic Name", command=delete_symbolic_name, width=30).pack(pady=5)
ttk.Button(button_frame, text="Refresh Port List", command=refresh_ports, width=30).pack(pady=5)

# Separator between Port Manager and File Upload sections
ttk.Separator(frame, orient='horizontal').pack(fill=tk.X, pady=20)

# File Selection Section
ttk.Label(frame, text="Select File (.ino or .bin):", font=("Helvetica", 12)).pack(pady=5)

# Entry field to display the selected file
file_path_var = tk.StringVar()
file_entry = ttk.Entry(frame, textvariable=file_path_var, font=("Helvetica", 10), width=80)
file_entry.pack(pady=5, fill=tk.X)

# Button to browse for a file
ttk.Button(frame, text="Browse", command=browse_file, width=30).pack(pady=5)

# Button for compile and upload actions
upload_button = ttk.Button(frame, text="Compile and Upload / Upload Binary", command=compile_and_upload, width=30)
upload_button.pack(pady=10)

# Progress bar for upload
progress_bar = ttk.Progressbar(frame, orient='horizontal', length=400, mode='determinate')
progress_bar.pack(pady=5)

# Status label to show concise status messages
status_label = ttk.Label(frame, text="", font=("Helvetica", 12))
status_label.pack(pady=5)

# Button to open console window moved to bottom corner
bottom_frame = ttk.Frame(root)
bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

ttk.Button(bottom_frame, text="Open Console Window", command=open_console_window, width=30).pack(side=tk.RIGHT, padx=5)

# Add copyright notice at the bottom
copyright_label = ttk.Label(bottom_frame, text="Copyrights reserved by Dognosis Corp/2024", font=("Helvetica", 10))
copyright_label.pack(side=tk.LEFT)

# Start the GUI event loop
root.mainloop()