import xlrd
import binascii
import time
import configparser
import datetime



#######################################
#Read data from config file
#######################################
config = configparser.ConfigParser()
config.read('temp_config.cfg')

#print('Reading in rat set temp configurations')
rat_set_temps = {}
for option in config.options('rat_set_temps'):
    rat_set_temps[float(option)] = float(config.get('rat_set_temps', option))

#print('Reading in rat maintainance temp change configurations')
rat_maint_dts = {}
for option in config.options('rat_maint_dts'):
    rat_maint_dts[float(option)] = float(config.get('rat_maint_dts', option))

#print('Reading in rat warming temp change configurations')
rat_warming_dts = {}
for option in config.options('rat_warming_dts'):
    rat_warming_dts[float(option)] = float(config.get('rat_warming_dts', option))

rat_warming_targets = {}
for option in config.options('rat_warming_targets'):
    rat_warming_targets[float(option)] = float(config.get('rat_warming_targets', option))

# rat_warming_modifiers = {}
# for option in config.options('rat_warming_modifiers'):
#     rat_warming_modifiers[float(option)] = float(config.get('rat_warming_modifiers', option))


def open_sheet(excel_file):
    workbook = xlrd.open_workbook(excel_file)
    sheet = workbook.sheet_by_index(0)
    return sheet

def read_current_temp(sheet, def_temp):
    try:
        current_temp = sheet.cell_value(int(config.get('GENERAL','excel_cell_y')),int(config.get('GENERAL','excel_cell_x')))
        if current_temp ==0x2A or current_temp ==0x00:
            print('Excel sheet has an empty value in the current temp cell, this may because experiment has just started and an average temperature has not been generated yet, setting read to default starting temp')
            return int(config.get('MAINTENANCE','default_starting_temp'))
        else:
            print('Reading in temperature of ' + str(current_temp)+ ' degrees')
            return float(current_temp)
    except Exception as e:
        print("Error reading current temp from excel, using previous temp")
        return def_temp


#BAD GLOBAL VARIABLE FOR TRACKING TIME DURING WARMING. FIX IF YOU HAVE THE TIME AND INCLINATION (works fine, just bad practice)
warming_time = config.getint('TESTING','starting_warming_time')

def calculate_set_temp(temp, phase, d_temp, last_set_temp): #gets closest value from tables in temp_config
    max_temp = config.getfloat('GENERAL', 'max_output_temp')
    min_temp = config.getfloat('GENERAL', 'min_output_temp')
    if phase == 0:
        local_temp = rat_set_temps.get(temp, rat_set_temps[min(rat_set_temps.keys(), key=lambda k: abs(k-temp))])
        return min(max_temp,max(min_temp,local_temp))
    elif phase == 1:
        local_temp = rat_set_temps.get(temp, rat_set_temps[min(rat_set_temps.keys(), key=lambda k: abs(k-temp))])+rat_maint_dts.get(d_temp,rat_maint_dts[min(rat_maint_dts.keys(), key=lambda k: abs(k-d_temp))])
        return min(max_temp,max(min_temp,local_temp))
    elif phase == 2:
        print('calculating set temp for warming hour:{}, threshold temp is {}'.format(int((warming_time/(60*60))),rat_warming_targets[int(warming_time/(60*60))] ))
        target_temp = rat_warming_targets[int(warming_time/(60*60))]
        local_temp = last_set_temp
        if abs(d_temp) <= int(config.get('WARMING','max_d_temp')):
            if temp >= target_temp:
                #local_temp = target_temp - rat_warming_modifiers.get(abs(temp-target_temp),rat_warming_modifiers[min(rat_warming_modifiers.keys(), key = lambda k:abs(k-abs(temp-target_temp)))])
                local_temp += rat_warming_dts.get(d_temp,rat_warming_dts[min(rat_warming_dts.keys(), key=lambda k: abs(k-d_temp))])
            elif temp < target_temp and rat_warming_dts.get(d_temp,rat_warming_dts[min(rat_warming_dts.keys(), key=lambda k: abs(k-d_temp))]) > 0:
                local_temp += rat_warming_dts.get(d_temp,rat_warming_dts[min(rat_warming_dts.keys(), key=lambda k: abs(k-d_temp))])
        return min(max_temp,max(min_temp,local_temp))
    else:
        return 0

def calculate_checksum(command): #part of generating command for temp controller
    checksum = 0
    for letter in command:
        checksum += int(ord(letter))
    return str(hex(checksum))[-2:]
        
def create_command(set_temp): #creates command to be read by the TC-720
    set_temp *= 100
    if set_temp < 0:
        set_temp = 2**16 - abs(int(set_temp))
    command = '1c'
    command += str(hex(int(set_temp)))[2:].zfill(4)
    command += calculate_checksum(command)
    return command




def write_out_file(command):
    with open('converted_command.txt','w') as out_file:
        out_file.write(command)
        out_file.close()

def write_out_temp(set_temp):
    print('Writing out temperature of ' + str(set_temp)+ ' degrees')
    with open('converted_command.txt','w') as out_file:
        out_file.write(create_command(set_temp))
        out_file.close()

def main(excel_file, phase, elapsed_time,temp_prev, temp_curr, d_temp, last_set_temp, sheet):
    try:
        new_sheet = open_sheet(excel_file)
    except:
        print("Could not read excel file, using previous values")
        new_sheet = sheet
    current_temp = read_current_temp(new_sheet, temp_prev)
    if current_temp > int(config.get('WARMING', 'max_body_temp')) or current_temp < int(config.get('WARMING','min_body_temp')):
        print('Reading in a temperature outside of expected range, defaulting to previous temperature')
        current_temp = temp_prev
    set_temp = calculate_set_temp(current_temp,phase, d_temp, last_set_temp)
    temp_prev = temp_curr
    temp_curr = current_temp
    d_temp = temp_curr- temp_prev
    with open('experiment_log.txt','a') as out_file:
        out_file.write('elapsed time ({:02d}:{:02d}:{:02d})---Phase:{}---'.format(int(elapsed_time/(60*60)),int(elapsed_time/60)%60,elapsed_time%60,phase))
        out_file.write('Reading:'+ str(current_temp)+ '---Sending:' + str(set_temp) + '---Temp Change:'+str(d_temp)+'\n')
        out_file.close()
    write_out_temp(set_temp)
    if phase == 0 and temp_curr > float(config.get('MAINTENANCE','target'))+1:
        return 0, temp_prev, temp_curr, d_temp, set_temp, new_sheet
    elif phase == 0:
        print('Advancing to phase 1: maintenance')
        with open('experiment_log.txt','a') as out_file:
            out_file.write('Advancing to Phase 1: Maintenance\n')
            out_file.close()
        return 1, temp_prev, temp_curr, d_temp, set_temp, new_sheet
    if phase == 2:
        return 2, temp_prev, temp_curr, d_temp, set_temp, new_sheet
    elif phase == 1 and elapsed_time >= 60*60*int(config.get('MAINTENANCE','duration')):
        print('Advancing to phase 2: rewarming')
        with open('experiment_log.txt','a') as out_file:
            out_file.write('Advancing to Phase 2: Rewarming\n')
            out_file.close()
        return 2, temp_prev, temp_curr, d_temp, set_temp, new_sheet
    else:
        return 1, temp_prev, temp_curr, d_temp, set_temp, new_sheet


#########################################
################Main Loop################
#########################################
try:
    with open('experiment_log.txt','a') as out_file:
        out_file.write('Begining Auto Temperature Control\n')
        out_file.write('Start Time:{}\n'.format(datetime.datetime.now()))
        out_file.close()
    elapsed_time = config.getint('TESTING','starting_elapsed_time')
    phase = int(config.get('TESTING','start_phase'))
    time_increment = int(config.get('GENERAL','update_frequency'))
    excel_file = config.get('GENERAL','excel_file')
    try:
        sheet = xlrd.open_workbook(excel_file).sheet_by_index(0)
    except:
        print('Initial excel read failed, please restart program')
        input('')
    print('Reading initial temp from Excel sheet (this may take a momment)')
    temp_prev = read_current_temp(open_sheet(excel_file), config.getint('MAINTENANCE','default_starting_temp'))
    if temp_prev > int(config.get('WARMING', 'max_body_temp')) or temp_prev < int(config.get('WARMING','min_body_temp')):
        print('Reading in a temperature outside of expected range, defaulting to default starting temp')
        temp_prev = config.getint('MAINTENANCE','default_starting_temp')
    temp_curr = temp_prev
    d_temp = 0
    set_temp = 0
    print('Begining temperature control\n')
    while True:
        phase, temp_prev, temp_curr, d_temp, set_temp, sheet= main(excel_file, phase, elapsed_time, temp_prev, temp_curr, d_temp, set_temp, sheet)
        print('temperature change:{}'.format(d_temp))
        print('elapsed time ({:02d}:{:02d}:{:02d})   Phase:{} \n'.format(int(elapsed_time/(60*60)),int(elapsed_time/60)%60,elapsed_time%60,phase))
        time.sleep(time_increment)
        elapsed_time += time_increment
        if phase == 2:
            warming_time += time_increment
        if int(warming_time/(60*60)) == int(config.get('WARMING','duration')):
            break
    with open('experiment_log.txt','a') as out_file:
        out_file.write('Experiment Complete\n\n')
        out_file.close()
    print('Experiment Complete')
    input('Press ENTER to exit. . .')
except Exception as e:
    with open('experiment_log.txt','a') as out_file:
        out_file.write(repr(e)+'\n')
        out_file.close()
    print(e)

    input('press ENTER to exit. . .')